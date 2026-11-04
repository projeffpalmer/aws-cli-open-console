# Copyright 2012-2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
"""Console URLs for tier-2/3 nodes from the resolver snapshots.

Inputs (``snapshots`` mapping):

``types``
    rows of ``types.tsv``: the ``go/list`` and ``go/create`` redirects of
    every CloudFormation type.  A redirect is *deep* when it is a 302 that
    is neither the console home nor a bare service home (a path ending in
    ``/home`` with no fragment and at most a ``region`` query).
``view_by_id``
    rows of ``view-by-id.tsv``: the ``go/view?resourceType=..&resourceId=``
    redirect for the sentinel id ``zz9idzz9``.  A 302 whose redirect holds
    the sentinel is the type's detail template; anything else means the type
    has no detail page.
``services``
    rows of ``services.tsv``.  Service homes are already on every node
    (``services.apply_service_layer``, which also applies
    ``services.yaml``), so the home a node falls back to is the placeholder
    it already carries; the rows are accepted for the contract's signature.

Per node with ``intent.resource_type`` (set by ``heuristics``):

- ``list`` -> the type's deep list page (``resolver:list``), else the
  service home kept with source ``derived``;
- ``create`` -> the type's deep create page (``resolver:create``), else the
  list rule;
- ``view`` -> the list rule;
- ``with_id`` -> the detail template whenever the type has one, the node
  has ``id_args`` and its verb is not ``create``; the source then gains
  ``+view`` where the contract defines that source
  (``resolver:list+view``).  A create command names a resource that does
  not exist yet (its id option is usually the new name), so a detail page
  would open a missing resource; curated overrides may still set one.

Templates come from ``services.templatize`` with the sentinel replaced by
``{id:raw}`` when the first id option ends in ``arn``/``arns``,
``{id:query}`` when the sentinel is a query parameter value before any
``#``, else ``{id}`` (contract section 1.1).  Nodes without a resource type
and custom subcommands keep the URL they have.
"""

import re
import urllib.parse

from console_db.overrides import BuildError
from console_db.services import is_console_home, templatize
from console_db.walk import iter_nodes

SENTINEL = 'zz9idzz9'
SENTINEL_MARK = 'zz9'
# The contract's url.source values for a page plus a detail template.
# 'derived+view' is not a contract source yet, so those nodes keep
# 'derived' alongside their with_id.  Create nodes never get a with_id.
VIEW_SOURCES = {'resolver:list': 'resolver:list+view'}
_QUERY_SENTINEL = re.compile(r'[?&][^=&#?]*=' + SENTINEL)


class TypePages:
    """List, create and detail pages per CloudFormation type."""

    def __init__(self, types_rows, view_by_id_rows):
        self.list_pages = {}
        self.create_pages = {}
        self.detail_redirects = {}
        for row in types_rows:
            name = row['resource_type']
            if is_deep(row.get('list_status'), row.get('list_redirect')):
                self.list_pages[name] = _template(row['list_redirect'])
            if is_deep(row.get('create_status'), row.get('create_redirect')):
                self.create_pages[name] = _template(row['create_redirect'])
        for row in view_by_id_rows:
            redirect = row.get('id_redirect') or ''
            if (
                row.get('id_status') == '302'
                and SENTINEL in redirect
                and usable(redirect)
            ):
                self.detail_redirects[row['resource_type']] = redirect


def usable(url):
    """False for a redirect the template language cannot hold.

    A literal brace cannot be escaped in a template; the 2026-11-04
    snapshot has two such redirects (a malformed ``$region}`` host for
    AWS::QuickSight::Analysis and a JSON filter for
    AWS::Inspector::AssessmentTemplate), which count as no page.
    """
    return '{' not in url and '}' not in url


def is_deep(status, url):
    """True when a resolver redirect is a page below the service home."""
    if status != '302' or not url or not usable(url):
        return False
    if is_console_home(url):
        return False
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    bare_home = (
        parts.path.endswith('/home')
        and not parts.fragment
        and all(key == 'region' for key, _ in query)
    )
    return not bare_home


def id_placeholder(redirect, id_arg):
    """The ``{id...}`` placeholder for a detail redirect and its id option."""
    name = (id_arg or '').lstrip('-')
    if name.endswith(('arn', 'arns')):
        return '{id:raw}'
    if _QUERY_SENTINEL.search(redirect.split('#', 1)[0]):
        return '{id:query}'
    return '{id}'


def detail_template(redirect, id_arg):
    """Template a sentinel redirect; raise when a sentinel survives."""
    if redirect.count(SENTINEL) != 1:
        raise BuildError(
            f'detail redirect must hold the sentinel once: {redirect!r}'
        )
    template, _, _ = templatize(redirect)
    template = template.replace(SENTINEL, id_placeholder(redirect, id_arg))
    if SENTINEL_MARK in template:
        raise BuildError(f'sentinel left in a template: {template!r}')
    return template


def assign_urls(root, snapshots, snapshot_date=None):
    """Set ``url`` on every tier-2/3 node that has a resource type."""
    pages = TypePages(
        snapshots.get('types') or [], snapshots.get('view_by_id') or []
    )
    for node in iter_nodes(root):
        if node['tier'] < 2 or node['kind'] not in ('operation', 'waiter'):
            continue
        intent = node.get('intent') or {}
        resource_type = intent.get('resource_type')
        if not resource_type:
            continue
        node['url'] = _url_for(
            node['url'], intent, resource_type, pages, snapshot_date
        )


def _url_for(current, intent, resource_type, pages, snapshot_date):
    verb = intent.get('verb')
    url = {'needs_account': False}
    if verb == 'create' and resource_type in pages.create_pages:
        url['best'] = pages.create_pages[resource_type]
        url['source'] = 'resolver:create'
        url['verified'] = snapshot_date
    elif resource_type in pages.list_pages:
        url['best'] = pages.list_pages[resource_type]
        url['source'] = 'resolver:list'
        url['verified'] = snapshot_date
    else:
        url['best'] = current['best']
        url['source'] = 'derived'
        url['verified'] = current.get('verified')
    id_args = intent.get('id_args') or []
    redirect = pages.detail_redirects.get(resource_type)
    if redirect and id_args and verb != 'create':
        url['with_id'] = detail_template(redirect, id_args[0])
        url['source'] = VIEW_SOURCES.get(url['source'], url['source'])
    return url


def _template(url):
    template, _, _ = templatize(url)
    return template
