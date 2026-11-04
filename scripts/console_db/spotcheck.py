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
"""Render the curated-URL spot-check page.

Writes ``review/spot-check.html``: a static page, grouped by tier-1
command, with one row per node whose ``url.source`` is ``curated``.  Each
row links the sample URL: the URL the first resolver case for that node
gives (``tests/unit/customizations/open_the_console_to_this/cases/``), else
``url.best`` rendered with the sample values of :mod:`console_db.verify`.
A signed-in reviewer opens the links by hand, because single-page consoles
cannot be checked unauthenticated.  No external assets, no JavaScript, and
the output is byte-identical for the same database and cases.
"""

import argparse
import collections
import html
import json
import os
import sys

if __package__ in (None, ''):
    # Run as a file: import the package from scripts/, not this directory.
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from console_db import verify  # noqa: E402

DEFAULT_OUT = os.path.join(verify.validate.HERE, 'review', 'spot-check.html')

STYLE = """
body { font: 14px/1.45 -apple-system, "Segoe UI", Helvetica, Arial,
  sans-serif; margin: 0 auto; max-width: 1200px; padding: 0 16px 48px;
  color: #1f2328; background: #ffffff; }
h1 { font-size: 22px; margin: 24px 0 8px; }
h2 { font-size: 17px; margin: 28px 0 6px; border-bottom: 1px solid #d0d7de;
  padding-bottom: 4px; }
h2 small { font-weight: normal; color: #59636e; }
p.lead { color: #33393f; max-width: 900px; }
nav { margin: 12px 0 0; line-height: 1.9; }
nav a { margin-right: 10px; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th, td { text-align: left; vertical-align: top; padding: 5px 8px;
  border-bottom: 1px solid #eaeef2; overflow-wrap: anywhere; }
th { background: #f6f8fa; font-weight: 600; }
col.path { width: 22%; } col.verb { width: 6%; } col.url { width: 44%; }
col.verified { width: 9%; } col.note { width: 19%; }
code { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
.argv { display: block; color: #59636e; margin-top: 2px; }
a { color: #0550ae; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  h2 { border-color: #30363d; } h2 small, .argv { color: #9198a1; }
  p.lead { color: #c9d1d9; } th { background: #161b22; }
  th, td { border-color: #21262d; } a { color: #58a6ff; }
}
"""


def curated_by_service(root):
    """``{tier1: [node, ...]}`` for curated nodes, sorted by path."""
    groups = collections.defaultdict(list)
    for node in verify.iter_nodes(root):
        if (node.get('url') or {}).get('source') != 'curated':
            continue
        tier1 = verify.tier1_name(node.get('path')) or node.get('name')
        groups[tier1].append(node)
    for nodes in groups.values():
        nodes.sort(key=lambda n: n.get('path') or '')
    return {name: groups[name] for name in sorted(groups)}


def sample_url(node, cases):
    """``(url, argv or None)`` for one curated node."""
    if cases:
        case, decision = cases[0]
        return decision.url, case['argv']
    values = verify.sample_values(node, cases)
    url, error = verify.render_sample((node.get('url') or {})['best'], values)
    return (url or f'(url.best could not be rendered: {error})'), None


def _e(text):
    return html.escape('' if text is None else str(text), quote=True)


def render_page(root, meta, cases_by_path):
    groups = curated_by_service(root)
    total = sum(len(nodes) for nodes in groups.values())
    out = [
        '<!doctype html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Curated console URL spot check</title>',
        f'<style>{STYLE}</style>',
        '</head>',
        '<body>',
        '<h1>Curated console URL spot check</h1>',
        '<p class="lead">One row per curated node of the '
        '<code>--in-console</code> database '
        f'({total} nodes in {len(groups)} tier-1 commands; awscli '
        f'{_e(meta.get("awscli"))}, snapshot {_e(meta.get("snapshot"))}). '
        'The links open the real console and need a signed-in console '
        'session in this browser. This page exists because single-page '
        'consoles answer the same way for good and bad routes when '
        'requested unauthenticated, so '
        '<code>scripts/verify-console-db</code> can check only the host '
        'and path; the fragment and the page itself need a human. The '
        'sample URL is the one the first resolver case for the node gives '
        '(its command line is shown under the link); without a case it is '
        '<code>url.best</code> rendered for us-west-2. Regenerate with '
        '<code>.venv/bin/python scripts/console_db/spotcheck.py</code>.'
        '</p>',
        '<nav>',
    ]
    for name in groups:
        out.append(f'<a href="#svc-{_e(name)}">{_e(name)}</a>')
    out.append('</nav>')
    for name, nodes in groups.items():
        tier1 = (root.get('children') or {}).get(name) or {}
        title = tier1.get('title')
        heading = _e(name)
        if title:
            heading += f' <small>{_e(title)}</small>'
        out.extend(
            [
                f'<h2 id="svc-{_e(name)}">{heading}</h2>',
                '<table>',
                '<colgroup><col class="path"><col class="verb">'
                '<col class="url"><col class="verified"><col class="note">'
                '</colgroup>',
                '<thead><tr><th>node</th><th>verb</th><th>sample URL</th>'
                '<th>verified</th><th>note</th></tr></thead>',
                '<tbody>',
            ]
        )
        for node in nodes:
            path = node.get('path') or ''
            url, argv = sample_url(node, cases_by_path.get(path, ()))
            intent = node.get('intent') or {}
            info = node.get('url') or {}
            argv_html = ''
            if argv:
                argv_html = (
                    '<code class="argv">aws ' f'{_e(" ".join(argv))}</code>'
                )
            if url.startswith('https://'):
                link = (
                    f'<a href="{_e(url)}" target="_blank" '
                    f'rel="noopener noreferrer"><code>{_e(url)}</code></a>'
                )
            else:
                link = _e(url)
            out.append(
                f'<tr><td><code>{_e(path)}</code></td>'
                f'<td>{_e(intent.get("verb") or "home")}</td>'
                f'<td>{link}{argv_html}</td>'
                f'<td>{_e(info.get("verified"))}</td>'
                f'<td>{_e(info.get("note"))}</td></tr>'
            )
        out.extend(['</tbody>', '</table>'])
    out.extend(['</body>', '</html>', ''])
    return '\n'.join(out)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        '--db',
        default=verify.DEFAULT_DB,
        help='database JSON to load (default: the committed file)',
    )
    parser.add_argument(
        '--out',
        default=DEFAULT_OUT,
        help='HTML file to write (default: review/spot-check.html)',
    )
    return parser.parse_args(argv)


def main(argv=None, err=None):
    err = err or sys.stderr
    args = parse_args(argv)
    try:
        with open(args.db, encoding='utf-8') as f:
            data = json.load(f)
        root = data['root']
        cases_by_path = verify.first_cases(root)
    except (OSError, ValueError, KeyError) as e:
        err.write(f'spotcheck: {e}\n')
        return 1
    page = render_page(root, data.get('generated') or {}, cases_by_path)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(page)
    return 0


if __name__ == '__main__':
    sys.exit(main())
