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
"""Re-request every distinct console URL in the database and report.

Loads the database JSON, renders ``url.best``, ``url.with_id``,
``url.with_ids`` and every ``url.variants`` template of every node whose
``url.source`` is selected, strips
the fragment, requests each distinct URL once with
:func:`console_db.validate.fetch` and classifies the answer with
:func:`console_db.validate.classify_response`
"""

import argparse
import collections
import concurrent.futures
import fnmatch
import json
import os
import sys
import urllib.parse

from awscli.customizations.open_the_console_to_this import urls as _urls
from console_db import validate

DEFAULT_DB = validate.DEFAULT_DB
DEFAULT_REPORT = os.path.join(validate.HERE, 'review', 'verify-report.md')
DEFAULT_SOURCES = 'curated,resolver:*'
MAX_WORKERS = 8
RETRIES = 2

SAMPLE_HOST = 'console.aws.amazon.com'
SAMPLE_REGION = 'us-west-2'
SAMPLE_ACCOUNT = '123456789012'
SAMPLE_ID = 'sample-id'
SAMPLE_PARAM = 'sample'
RENDER_ERROR = 'RENDER-ERROR'
# A param no case gives renders as ``sample``, except where that would put
# ``sample`` in the host or the region.
_TYPED_SAMPLES = {
    'arn_region': SAMPLE_REGION,
    'arn_account': SAMPLE_ACCOUNT,
}


class _Samples(dict):
    """Template values; any name not given renders as ``sample``."""

    def get(self, name, default=None):
        return dict.get(self, name, SAMPLE_PARAM)


def iter_nodes(root):
    """Yield every node, depth first, children in sorted order."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        children = node.get('children') or {}
        for name in sorted(children, reverse=True):
            stack.append(children[name])


def tier1_name(path):
    parts = (path or '').split('.')
    return parts[1] if len(parts) > 1 else None


def case_stems(root, tier1):
    """Case file stems that may hold cases for nodes under ``tier1``.

    The tier-1 command's own file, plus ``customs`` for the custom tier-1
    commands (contract section 2).
    """
    stems = [tier1]
    node = (root.get('children') or {}).get(tier1) or {}
    if node.get('kind') == 'custom' and tier1 != 'customs':
        stems.append('customs')
    return stems


def first_cases(root, harness=None, tier1_names=None):
    """Return ``{node_path: [(case, decision), ...]}`` in file order.

    Only the case files named after each tier-1 command (and
    ``customs.yaml`` for custom commands) are read; a case counts for the
    node its argv resolves to.
    """
    harness = harness or validate._harness()
    names = tier1_names
    if names is None:
        names = sorted((root.get('children') or {}).keys())
    loaded = {}
    out = collections.defaultdict(list)
    for tier1 in names:
        for stem in case_stems(root, tier1):
            path = os.path.join(harness.CASES_DIR, f'{stem}.yaml')
            if not os.path.isfile(path):
                continue
            if stem not in loaded:
                loaded[stem] = []
                for _, case in harness.load_case_file(path):
                    argv = case['argv']
                    decision = harness.resolve(
                        root, argv[0], argv[1:], harness.case_context(case)
                    )
                    loaded[stem].append((case, decision))
            for case, decision in loaded[stem]:
                if tier1_name(decision.node_path) == tier1:
                    out[decision.node_path].append((case, decision))
    return out


def param_samples(node, cases):
    """``{param: value}`` for the node's curated params.

    The value is the one the first case resolving to this node gives that
    param; ``sample`` when no case gives it (the sample region / account
    for an ``arn_region`` / ``arn_account`` param).
    """
    params = (node.get('intent') or {}).get('params') or {}
    samples = {}
    for name in sorted(params):
        parse = (params[name] or {}).get('parse')
        samples[name] = _TYPED_SAMPLES.get(parse, SAMPLE_PARAM)
        for _, decision in cases:
            value = (decision.params or {}).get(name)
            if value is not None:
                samples[name] = value
                break
    return samples


def sample_values(node, cases):
    values = _Samples(param_samples(node, cases))
    values.update(
        host=SAMPLE_HOST,
        region=SAMPLE_REGION,
        account=SAMPLE_ACCOUNT,
        id=SAMPLE_ID,
        ids=SAMPLE_ID,
    )
    return values


def node_templates(node):
    """Yield ``(label, template)`` for every template of ``node``."""
    url = node.get('url') or {}
    for key in ('best', 'with_id', 'with_ids'):
        if url.get(key):
            yield key, url[key]
    for index, variant in enumerate(url.get('variants') or ()):
        if variant.get('template'):
            yield f'variants[{index}]', variant['template']


def render_sample(template, values):
    """Render ``template``; ``(url, None)`` or ``(None, error)``."""
    try:
        return _urls.render(template, values), None
    except (KeyError, ValueError) as e:
        return None, f'{type(e).__name__}: {e}'


def source_selected(source, patterns):
    return any(fnmatch.fnmatchcase(source or '', p) for p in patterns)


def collect(root, patterns, cases_by_path=None):
    """Return ``(urls, render_errors)``.

    ``urls`` maps each distinct defragmented URL to a sorted list of
    ``(node_path, label, source)``; ``render_errors`` is a sorted list of
    ``(node_path, label, source, error)``.
    """
    if cases_by_path is None:
        cases_by_path = first_cases(root)
    urls = collections.defaultdict(set)
    errors = []
    for node in iter_nodes(root):
        source = (node.get('url') or {}).get('source')
        if not source_selected(source, patterns):
            continue
        path = node.get('path') or ''
        values = sample_values(node, cases_by_path.get(path, ()))
        for label, template in node_templates(node):
            rendered, error = render_sample(template, values)
            if rendered is None:
                errors.append((path, label, source, error))
                continue
            url = urllib.parse.urldefrag(rendered)[0]
            urls[url].add((path, label, source))
    return {u: sorted(users) for u, users in urls.items()}, sorted(errors)


def check(url, fetcher=validate.fetch, retries=RETRIES):
    """Return ``(verdict, status, location, reason)`` for one URL.

    SKIP for partition hosts this environment cannot reach; a connection
    error (status ``000``) is retried ``retries`` times.
    """
    reason = validate.skip_reason(url)
    if reason is not None:
        return validate.SKIP, '-', '', reason
    for _ in range(retries + 1):
        status, location = fetcher(url)
        if status != '000':
            break
    verdict, reason = validate.classify_response(url, status, location)
    return verdict, status, location, reason


def check_all(urls, workers=MAX_WORKERS, checker=check, progress=None):
    """Check every URL with at most 8 threads; ``{url: result}``."""
    workers = max(1, min(int(workers), MAX_WORKERS))
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(checker, url): url for url in urls}
        for done, future in enumerate(
            concurrent.futures.as_completed(futures), 1
        ):
            results[futures[future]] = future.result()
            if progress is not None and done % 250 == 0:
                progress.write(f'verify-console-db: {done}/{len(urls)}\n')
    return results


def gating(source):
    """True when a FAIL of a URL used by ``source`` fails the run."""
    return source == 'curated' or (source or '').startswith('resolver:')


def _md(text):
    return str(text).replace('|', '\\|')


def write_report(out, meta, results, urls, errors, args_line):
    verdicts = (validate.PASS, validate.FAIL, validate.SKIP)
    totals = collections.Counter(r[0] for r in results.values())
    by_source = collections.defaultdict(collections.Counter)
    for url, result in results.items():
        for source in sorted({u[2] for u in urls[url]}):
            by_source[source][result[0]] += 1
    out.write('# Console URL verification report\n\n')
    out.write(
        'Generated by `scripts/verify-console-db` '
        f'(`{args_line}`) from the database built by awscli '
        f'{meta.get("awscli")} against the {meta.get("snapshot")} '
        'snapshots.  Each distinct host+path+query (fragment stripped) '
        f'rendered with host `{SAMPLE_HOST}`, region `{SAMPLE_REGION}`, '
        f'account `{SAMPLE_ACCOUNT}` and sample ids was requested once, '
        'unauthenticated and without following redirects, and classified '
        'by `console_db.validate.classify_response` (contract section 6, '
        'rule 3).\n\n'
    )
    out.write('## Totals by verdict\n\n| verdict | URLs |\n|---|---|\n')
    for verdict in verdicts:
        out.write(f'| {verdict} | {totals[verdict]} |\n')
    out.write(f'| total | {sum(totals.values())} |\n')
    if errors:
        out.write(f'| {RENDER_ERROR} (templates) | {len(errors)} |\n')
    out.write(
        '\n## Totals by url.source\n\n'
        'A URL shared by nodes of several sources counts under each.\n\n'
        '| source | PASS | FAIL | SKIP |\n|---|---|---|---|\n'
    )
    for source in sorted(by_source):
        row = ' | '.join(str(by_source[source][v]) for v in verdicts)
        out.write(f'| {_md(source)} | {row} |\n')
    fails = sorted(u for u, r in results.items() if r[0] == validate.FAIL)
    out.write(f'\n## FAIL ({len(fails)})\n\n')
    if not fails:
        out.write('None.\n')
    for url in fails:
        _, status, location, reason = results[url]
        detail = f' -> `{location}`' if location else ''
        out.write(f'- `{url}` {status}{detail} ({_md(reason)})\n')
        for path, label, source in urls[url]:
            out.write(f'  - `{path}` {label} ({source})\n')
    if errors:
        out.write(
            f'\n## Templates that could not be rendered ({len(errors)})\n\n'
        )
        for path, label, source, error in errors:
            out.write(f'- `{path}` {label} ({source}): {_md(error)}\n')
    skips = sorted(u for u, r in results.items() if r[0] == validate.SKIP)
    out.write(f'\n## SKIP ({len(skips)})\n\n')
    if not skips:
        out.write('None.\n')
    for url in skips:
        users = ', '.join(f'`{p}` {label}' for p, label, _ in urls[url])
        out.write(f'- `{url}` ({results[url][3]}): {users}\n')


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        '--db',
        default=DEFAULT_DB,
        help='database JSON to load (default: the committed file)',
    )
    parser.add_argument(
        '--report',
        default=DEFAULT_REPORT,
        help='Markdown report to write (default: review/verify-report.md)',
    )
    parser.add_argument(
        '--sources',
        default=DEFAULT_SOURCES,
        help=(
            'comma-separated url.source values or fnmatch patterns '
            f'(default: {DEFAULT_SOURCES}); add derived, service-home or '
            'console-home to check those too'
        ),
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        metavar='N',
        help='check only the first N distinct URLs in sorted order',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=MAX_WORKERS,
        help=f'threads (at most {MAX_WORKERS})',
    )
    return parser.parse_args(argv)


def main(argv=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    args = parse_args(argv)
    patterns = [p.strip() for p in args.sources.split(',') if p.strip()]
    try:
        with open(args.db, encoding='utf-8') as f:
            data = json.load(f)
        root = data['root']
    except (OSError, ValueError, KeyError) as e:
        err.write(f'verify-console-db: {e}\n')
        return 1
    try:
        cases_by_path = first_cases(root)
    except (OSError, ValueError) as e:
        err.write(f'verify-console-db: {e}\n')
        return 1
    urls, errors = collect(root, patterns, cases_by_path)
    selected = sorted(urls)
    if args.limit is not None:
        selected = selected[: max(0, args.limit)]
    err.write(
        f'verify-console-db: {len(urls)} distinct URLs for '
        f'{",".join(patterns)}; checking {len(selected)}\n'
    )
    results = check_all(selected, args.workers, progress=err)
    args_line = ' '.join(
        ['--sources', ','.join(patterns)]
        + ([] if args.limit is None else ['--limit', str(args.limit)])
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, 'w', encoding='utf-8', newline='\n') as f:
        write_report(
            f,
            data.get('generated') or {},
            results,
            {u: urls[u] for u in selected},
            errors,
            args_line,
        )
    totals = collections.Counter(r[0] for r in results.values())
    gated = 0
    for url in sorted(results):
        verdict, status, location, reason = results[url]
        if verdict != validate.FAIL:
            continue
        detail = f' -> {location}' if location else ''
        out.write(f'FAIL {status} {url}{detail} ({reason})\n')
        if any(gating(source) for _, _, source in urls[url]):
            gated += 1
    gated_errors = sum(1 for e in errors if gating(e[2]))
    out.write(
        f'{len(results)} URLs: {totals[validate.PASS]} passed, '
        f'{totals[validate.FAIL]} failed ({gated} curated/resolver), '
        f'{totals[validate.SKIP]} skipped; {len(errors)} templates could '
        f'not be rendered; report: {args.report}\n'
    )
    return 1 if gated or gated_errors else 0
