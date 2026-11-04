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
"""Documentation URLs for every node.

- root: ``https://docs.aws.amazon.com/`` (source ``curated``);
- tier 1: the curated landing from ``docs.yaml`` (source ``curated``), else
  ``https://docs.aws.amazon.com/<name>/`` when ``snapshots/docs.tsv`` says it
  answered 200 or 301 (source ``probe``), else the CLI reference index
  (source ``reference-index``); the reference index is the ``fallback`` of
  the first two;
- tier 2 and 3: the CLI reference page by pattern (source ``pattern``):
  ``<svc>/<op>.html``, ``<svc>/<group>/<op>.html``, and
  ``<svc>/<group>/index.html`` for a group, which is the page the CLI's own
  help links to for a command that has subcommands.
"""

from console_db.overrides import BuildError
from console_db.walk import tier1_nodes

DOCS_HOME = 'https://docs.aws.amazon.com/'
CLI_REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'
LANDING_OK = frozenset(['200', '301'])
_DOCS_KEYS = frozenset(['landing'])


def reference_url(names, has_children):
    """CLI reference page for the command named by ``names`` (no 'aws')."""
    base = CLI_REFERENCE + '/'.join(names)
    return base + ('/index.html' if has_children else '.html')


def assign_docs(root, docs_tsv_rows, overrides):
    """Set ``docs`` on every node; ``overrides`` is the docs.yaml mapping."""
    overrides = overrides or {}
    rows = {row['cli_service']: row for row in docs_tsv_rows}
    nodes = dict(tier1_nodes(root))
    for name in sorted(overrides):
        entry = overrides[name]
        if name not in nodes:
            raise BuildError(
                f'docs.yaml: unknown tier-1 name {name!r} '
                '(not in the command tree)'
            )
        if not isinstance(entry, dict) or set(entry) - _DOCS_KEYS:
            raise BuildError(
                f'docs.yaml: {name}: expected a mapping with only '
                f'{sorted(_DOCS_KEYS)}'
            )
    root['docs'] = {'best': DOCS_HOME, 'source': 'curated', 'fallback': None}
    for name, node in nodes.items():
        index = reference_url([name], True)
        landing = (overrides.get(name) or {}).get('landing')
        row = rows.get(name) or {}
        if landing:
            docs = {'best': landing, 'source': 'curated', 'fallback': index}
        elif row.get('docs_landing_status') in LANDING_OK:
            docs = {
                'best': f'{DOCS_HOME}{name}/',
                'source': 'probe',
                'fallback': index,
            }
        else:
            docs = {'best': index, 'source': 'reference-index'}
            docs['fallback'] = None
        node['docs'] = docs
        _assign_patterns(node, [name])


def _assign_patterns(parent, names):
    for name, node in sorted((parent.get('children') or {}).items()):
        child_names = names + [name]
        has_children = bool(node.get('children'))
        node['docs'] = {
            'best': reference_url(child_names, has_children),
            'source': 'pattern',
            'fallback': None,
        }
        _assign_patterns(node, child_names)
