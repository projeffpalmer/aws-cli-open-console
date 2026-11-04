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
"""Service layer: console slug, scope, home URL and namespaces per tier 1.

Inputs are the rows of ``snapshots/services.tsv`` (the resolver's redirect
for ``go/view?service=<name>&region=us-west-2``) and the entries of
``overrides/services.yaml``.  A redirect that lands on ``console/home`` means
the resolver does not know the name; every such name needs an entry in
``services.yaml``, otherwise the build stops.

``services.yaml`` entries are keyed by tier-1 name and accept these keys:

``same_as``
    reuse another tier-1 node's console and home URL (source
    ``service-home``).
``source: console-home``
    use the console home page.
``home``
    a curated URL template (source ``curated`` unless ``source`` says
    otherwise); ``slug`` and ``scope`` default to what the template shows.
``namespaces``, ``title``, ``verified``, ``note``
    replace the generated value.

The root gets the console home (source ``curated``).  Tier-2 and tier-3
nodes then get their service's home URL as a placeholder
(source ``service-home``, or ``console-home`` when the service itself only
has the console home) until a later step finds a better page.
"""

import re
import urllib.parse

from console_db.overrides import BuildError
from console_db.walk import iter_nodes, tier1_nodes

PROBE_REGION = 'us-west-2'
REGIONAL_PROBE_HOST = f'{PROBE_REGION}.console.aws.amazon.com'
GLOBAL_HOST = 'console.aws.amazon.com'
REGIONAL_PREFIX = 'https://{region}.{host}'
GLOBAL_PREFIX = 'https://{host}'
CONSOLE_HOME = 'https://{host}/console/home?region={region}'
CONSOLE_SLUG = 'console'

_SERVICE_KEYS = frozenset(
    [
        'same_as',
        'source',
        'home',
        'slug',
        'scope',
        'namespaces',
        'title',
        'verified',
        'note',
    ]
)
_SOURCES = frozenset(['curated', 'console-home', 'resolver:service'])
_SCOPES = frozenset(['regional', 'global', 'special'])
_NORMALIZE = re.compile(r'[^a-z0-9]')


def templatize(url):
    """Turn a us-west-2 resolver redirect into ``(template, scope, slug)``.

    ``us-west-2.console.aws.amazon.com`` is regional and becomes
    ``https://{region}.{host}``; ``console.aws.amazon.com`` is global and
    becomes ``https://{host}``; in both, ``region=us-west-2`` becomes
    ``region={region}``.  Any other host is special and kept literal.
    ``slug`` is the first path segment.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not parts.netloc:
        raise BuildError(f'not an absolute https URL: {url!r}')
    if '{' in url or '}' in url:
        raise BuildError(f'URL contains a template brace: {url!r}')
    rest = url[len(f'https://{parts.netloc}') :]
    slug = parts.path.lstrip('/').split('/')[0]
    if parts.netloc == REGIONAL_PROBE_HOST:
        scope, template = 'regional', REGIONAL_PREFIX + _region_param(rest)
    elif parts.netloc == GLOBAL_HOST:
        scope, template = 'global', GLOBAL_PREFIX + _region_param(rest)
    else:
        scope, template = 'special', url
    return template, scope, slug


def scope_of(template):
    """Return the scope a URL template's host form implies."""
    if template.startswith(REGIONAL_PREFIX + '/'):
        return 'regional'
    if template.startswith(GLOBAL_PREFIX + '/'):
        return 'global'
    return 'special'


def is_console_home(url):
    path = urllib.parse.urlsplit(url).path
    return path.rstrip('/') == '/console/home'


def apply_service_layer(
    root, services_tsv_rows, overrides, namespaces=(), snapshot_date=None
):
    """Fill ``console``, ``url`` and ``title`` on tier 1, ``url`` below.

    ``services_tsv_rows`` are dicts with ``cli_service``, ``http_status``
    and ``redirect_url``; ``overrides`` is the ``services.yaml`` mapping;
    ``namespaces`` are the CloudFormation namespaces known to the snapshot
    (``EC2`` for ``AWS::EC2::Instance``), used to match service names;
    ``snapshot_date`` is the ``verified`` date of resolver-derived URLs.
    """
    overrides = overrides or {}
    rows = {row['cli_service']: row for row in services_tsv_rows}
    known_ns = sorted(set(namespaces))
    nodes = dict(tier1_nodes(root))
    for name in sorted(overrides):
        if name not in nodes:
            raise BuildError(
                f'services.yaml: unknown tier-1 name {name!r} '
                '(not in the command tree)'
            )
        _check_entry(name, overrides[name], nodes, known_ns, overrides)
    resolved = {}
    deferred = []
    for name, node in nodes.items():
        entry = overrides.get(name) or {}
        if 'same_as' in entry:
            deferred.append(name)
            continue
        resolved[name] = _resolve_home(
            name, entry, rows.get(name), snapshot_date
        )
    for name in deferred:
        target = overrides[name]['same_as']
        home = dict(resolved[target])
        home['source'] = 'service-home'
        home['note'] = f'same console as {target}'
        resolved[name] = home
    for name, node in nodes.items():
        entry = overrides.get(name) or {}
        home = resolved[name]
        if 'same_as' in entry:
            target_node = nodes[entry['same_as']]
            ns = (target_node.get('console') or {}).get('namespaces')
            if ns is None:
                ns = _match_namespaces(target_node, known_ns)
        else:
            ns = None
        if 'namespaces' in entry:
            ns = list(entry['namespaces'])
        elif ns is None:
            ns = _match_namespaces(node, known_ns)
        if node['kind'] == 'service':
            node['console'] = {
                'slug': home['slug'],
                'scope': home['scope'],
                'namespaces': ns,
            }
        node['url'] = {
            'best': home['best'],
            'source': home['source'],
            'verified': home['verified'],
            'needs_account': False,
            'note': entry.get('note', home.get('note')),
        }
        if 'title' in entry:
            node['title'] = entry['title']
    for _name, node in nodes.items():
        _fill_descendants(node)
    root['url'] = {
        'best': CONSOLE_HOME,
        'source': 'curated',
        'verified': snapshot_date,
        'needs_account': False,
    }


def _resolve_home(name, entry, row, snapshot_date):
    source = entry.get('source')
    if source == 'console-home':
        return {
            'best': CONSOLE_HOME,
            'slug': CONSOLE_SLUG,
            'scope': 'global',
            'source': 'console-home',
            'verified': entry.get('verified', snapshot_date),
        }
    if 'home' in entry:
        template = entry['home']
        return {
            'best': template,
            'slug': entry.get('slug') or _slug_of(template),
            'scope': entry.get('scope') or scope_of(template),
            'source': source or 'curated',
            'verified': entry.get('verified'),
        }
    if row is None:
        raise BuildError(
            f'{name}: no row in snapshots/services.tsv and no entry in '
            'overrides/services.yaml; refresh the snapshot '
            '(scripts/snapshot-console-resolver capture services) or add one'
        )
    redirect = row.get('redirect_url') or ''
    if row.get('http_status') != '302' or not redirect:
        raise BuildError(
            f'{name}: services.tsv has status {row.get("http_status")!r}; '
            'add an entry to overrides/services.yaml'
        )
    if is_console_home(redirect):
        raise BuildError(
            f'{name}: the resolver does not know this name (redirect to '
            'console/home); add an entry to overrides/services.yaml'
        )
    template, scope, slug = templatize(redirect)
    return {
        'best': template,
        'slug': entry.get('slug') or slug,
        'scope': entry.get('scope') or scope,
        'source': source or 'resolver:service',
        'verified': entry.get('verified', snapshot_date),
    }


def _check_entry(name, entry, nodes, known_ns, overrides):
    if not isinstance(entry, dict):
        raise BuildError(f'services.yaml: {name}: expected a mapping')
    unknown = sorted(set(entry) - _SERVICE_KEYS)
    if unknown:
        raise BuildError(f'services.yaml: {name}: unknown keys {unknown}')
    if 'same_as' in entry:
        target = entry['same_as']
        if target not in nodes:
            raise BuildError(
                f'services.yaml: {name}: same_as {target!r} is not a '
                'tier-1 name'
            )
        if 'same_as' in (overrides.get(target) or {}):
            raise BuildError(
                f'services.yaml: {name}: same_as target {target!r} has a '
                'same_as of its own'
            )
        if set(entry) & {'home', 'source', 'slug', 'scope'}:
            raise BuildError(
                f'services.yaml: {name}: same_as cannot be combined with '
                'home, source, slug or scope'
            )
    if 'source' in entry and entry['source'] not in _SOURCES:
        raise BuildError(
            f'services.yaml: {name}: source must be one of {sorted(_SOURCES)}'
        )
    if 'scope' in entry and entry['scope'] not in _SCOPES:
        raise BuildError(
            f'services.yaml: {name}: scope must be one of {sorted(_SCOPES)}'
        )
    for ns in entry.get('namespaces') or []:
        if known_ns and ns not in known_ns:
            raise BuildError(
                f'services.yaml: {name}: namespace {ns!r} is not in '
                'snapshots/resource-types.txt'
            )


def _match_namespaces(node, known_ns):
    """Namespaces whose normalized name equals the CLI name or service id."""
    meta = node.get('_meta') or {}
    keys = {_normalize(node['name']), _normalize(meta.get('service_id'))}
    keys.discard('')
    return [ns for ns in known_ns if _normalize(ns) in keys]


def _fill_descendants(service_node):
    home = service_node['url']
    source = home['source']
    if source != 'console-home':
        source = 'service-home'
    for node in iter_nodes(service_node):
        if node is service_node:
            continue
        node['intent'] = None
        node['url'] = {
            'best': home['best'],
            'source': source,
            'verified': home['verified'],
            'needs_account': False,
        }


def _region_param(rest):
    return rest.replace(f'region={PROBE_REGION}', 'region={region}')


def _slug_of(template):
    path = urllib.parse.urlsplit(template.replace('{', '').replace('}', ''))
    return path.path.lstrip('/').split('/')[0]


def _normalize(text):
    return _NORMALIZE.sub('', (text or '').lower())
