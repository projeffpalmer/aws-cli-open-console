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
"""Check the override files against the resolver cases.

Loads the database JSON, applies ``scripts/console_db/overrides/*.yaml`` in
memory, runs every case under
``tests/unit/customizations/open_the_console_to_this/cases/`` (or only the
named ``cases/<NAME>.yaml`` files) through ``resolve()`` and prints one line
per case.  With ``--check-urls`` it also requests each distinct expected URL
(fragment stripped) once, unauthenticated and without following redirects,
and classifies the answer with :func:`classify_response` (contract section
6, rule 3).  URLs on aws-us-gov and aws-cn hosts are not requested and are
reported as SKIP.  Exit status 1 when a case or a URL fails.  Stdlib plus
ruamel.yaml only.
"""

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from console_db import overrides as overrides_mod

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_DB = os.path.join(
    REPO, 'awscli', 'data', 'open_the_console_to_this', 'commands.json'
)
DEFAULT_OVERRIDES = os.path.join(HERE, 'overrides')
TIMEOUT = 25

PASS = 'PASS'
FAIL = 'FAIL'
SKIP = 'SKIP'
SKIP_REASON = 'partition host not reachable from this environment'
# Console host per partition: the bare host or any subdomain of it.
CONSOLE_HOSTS = {
    'aws': 'console.aws.amazon.com',
    'aws-us-gov': 'console.amazonaws-us-gov.com',
    'aws-cn': 'console.amazonaws.cn',
}
# Partitions whose hosts this environment's egress proxy refuses.
_SKIPPED_PARTITIONS = {
    'aws-us-gov': 'amazonaws-us-gov.com',
    'aws-cn': 'amazonaws.cn',
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn every 3xx into an HTTPError so its Location can be read."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _host_matches(host, domain):
    return host == domain or host.endswith('.' + domain)


def console_partition(host):
    """Return the partition whose console ``host`` belongs to, or None."""
    host = (host or '').lower()
    for partition, console in sorted(CONSOLE_HOSTS.items()):
        if _host_matches(host, console):
            return partition
    return None


def skip_reason(url):
    """Return why ``url`` is not requested at all, or None."""
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    for domain in _SKIPPED_PARTITIONS.values():
        if _host_matches(host, domain):
            return SKIP_REASON
    return None


def _trailing_slash_change(source, target):
    """Return ``'without'`` or ``'with'`` when ``target`` is ``source``
    with one trailing slash removed from or added to the path (same
    scheme, host and query), else None.
    """
    if (
        source.scheme.lower() != target.scheme.lower()
        or source.netloc.lower() != target.netloc.lower()
        or source.query != target.query
    ):
        return None
    if source.path == target.path + '/' and target.path:
        return 'without'
    if target.path == source.path + '/' and source.path:
        return 'with'
    return None


def classify_response(url, status, location):
    """Apply contract section 6, rule 3 to one unredirected answer.

    ``status`` is the HTTP status (int or str; ``'000'`` when the host
    could not be reached) and ``location`` the Location header (or the
    connection error).  Returns ``(verdict, reason)`` with ``verdict``
    PASS or FAIL.
    """
    try:
        code = int(status)
    except (TypeError, ValueError):
        code = 0
    if code == 0:
        return FAIL, f'unreachable: {location}' if location else 'unreachable'
    if code == 200:
        return PASS, '200'
    if code != 302:
        return FAIL, f'status {code}'
    location = location or ''
    if 'signin' in location:
        return PASS, '302 to sign-in'
    source = urllib.parse.urlsplit(url)
    target = urllib.parse.urlsplit(urllib.parse.urljoin(url, location))
    source_host = (source.hostname or '').lower()
    target_host = (target.hostname or '').lower()
    target_partition = console_partition(target_host)
    if source.path.startswith('/go/'):
        if target_partition is not None:
            return PASS, '/go/ redirect to a console host'
        return FAIL, '/go/ redirect to a non-console host'
    slash = _trailing_slash_change(source, target)
    if slash is not None:
        return PASS, f'302 to the same path {slash} a trailing slash'
    source_partition = console_partition(source_host)
    if (
        source_partition is not None
        and target_partition == source_partition
        and target_host != source_host
        and target.path == source.path
    ):
        return PASS, '302 to the same path on another console host'
    return FAIL, '302 to another page'


def fetch(url, opener=None):
    """GET ``url`` once without following redirects.

    Returns ``(status, location)``; ``status`` is ``'000'`` and
    ``location`` the error text when the host could not be reached.  The
    environment's proxy and CA settings apply (``https_proxy``,
    ``SSL_CERT_FILE``).
    """
    opener = opener or urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, method='GET')
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return str(response.status), ''
    except urllib.error.HTTPError as error:
        location = error.headers.get('Location', '') or ''
        error.close()
        return str(error.code), location
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        return '000', str(e)


def check_url(url, opener=None):
    """Return ``(verdict, status, location, reason)`` for ``url``.

    SKIP URLs are not requested; their status is ``'-'``.
    """
    reason = skip_reason(url)
    if reason is not None:
        return SKIP, '-', '', reason
    status, location = fetch(url, opener)
    verdict, reason = classify_response(url, status, location)
    return verdict, status, location, reason


def _harness():
    """Import the case loader shared with ``test_resolver_cases.py``."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from tests.unit.customizations.open_the_console_to_this import (
        test_resolver_cases,
    )

    return test_resolver_cases


def load_root(db_path, overrides_dir):
    with open(db_path, encoding='utf-8') as f:
        data = json.load(f)
    root = data['root']
    loaded = overrides_mod.load_overrides(overrides_dir)
    overrides_mod.apply_overrides(root, loaded)
    return root, len(loaded)


def run_cases(root, cases, run_case, out):
    failed = 0
    for case_id, case in cases:
        decision, problems = run_case(root, case)
        if problems:
            failed += 1
            out.write(f'FAIL {case_id}: {"; ".join(problems)}\n')
        else:
            out.write(f'PASS {case_id}\n')
    return failed


def check_urls(cases, out, checker=check_url):
    """Check each distinct expected URL; return ``{verdict: count}``."""
    urls = sorted({urllib.parse.urldefrag(c['url'])[0] for _, c in cases})
    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    for url in urls:
        verdict, status, location, reason = checker(url)
        counts[verdict] += 1
        detail = f' -> {location}' if location else ''
        out.write(f'URL {verdict} {status} {url}{detail} ({reason})\n')
    return counts


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n\n')[0],
    )
    parser.add_argument(
        '--service',
        action='extend',
        nargs='+',
        default=[],
        metavar='NAME',
        help='run only cases/NAME.yaml (repeatable)',
    )
    parser.add_argument(
        '--check-urls',
        action='store_true',
        help='also GET each distinct expected URL (network)',
    )
    parser.add_argument(
        '--db',
        default=DEFAULT_DB,
        help='database JSON to load (default: the committed file)',
    )
    parser.add_argument(
        '--overrides-dir',
        default=DEFAULT_OVERRIDES,
        help='directory holding the override YAML files',
    )
    return parser.parse_args(argv)


def main(argv=None, out=None):
    out = out or sys.stdout
    args = parse_args(argv)
    try:
        harness = _harness()
        cases = harness.load_cases(args.service or None)
    except (OSError, ValueError) as e:
        sys.stderr.write(f'validate-console-overrides: {e}\n')
        return 1
    try:
        root, count = load_root(args.db, args.overrides_dir)
    except (OSError, ValueError, KeyError, overrides_mod.BuildError) as e:
        sys.stderr.write(f'validate-console-overrides: {e}\n')
        return 1
    out.write(
        f'# {args.db} with {count} node overrides from '
        f'{args.overrides_dir}\n'
    )
    failed = run_cases(root, cases, harness.run_case, out)
    out.write(
        f'{len(cases)} cases: {len(cases) - failed} passed, '
        f'{failed} failed\n'
    )
    url_failed = 0
    if args.check_urls:
        counts = check_urls(cases, out)
        url_failed = counts[FAIL]
        out.write(
            f'{sum(counts.values())} URLs: {counts[PASS]} passed, '
            f'{counts[FAIL]} failed, {counts[SKIP]} skipped\n'
        )
    return 1 if failed or url_failed else 0
