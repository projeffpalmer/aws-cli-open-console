"""Capture and check the console resolver snapshots in ``snapshots/``.

Every snapshot is a TSV file whose first column(s) name the probed input and
whose remaining columns record, per probe URL, the HTTP status and (for most
probes) the raw ``Location`` header.  Requests are plain unauthenticated GETs
that never follow redirects; the redirect itself is the data.

Usage (through ``scripts/snapshot-console-resolver``)::

    snapshot-console-resolver capture NAME [NAME ...]
    snapshot-console-resolver --check [--sample N] [NAME ...]
    snapshot-console-resolver --refresh-types [PIP_REQUIREMENT]

NAME is one of: services, types, view-samples, view-by-id, docs.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(HERE, 'snapshots')
RESOURCE_TYPES_FILE = os.path.join(SNAPSHOT_DIR, 'resource-types.txt')

CONSOLE_GO = 'https://console.aws.amazon.com/go/'
DOCS_HOST = 'https://docs.aws.amazon.com/'
REGION = 'us-west-2'
# Sentinel resource ids for view-by-id; sent URL-encoded, so the slash form
# goes over the wire as zz9%2Fid%2Fzz9.
SENTINEL_ID = 'zz9idzz9'
SENTINEL_SLASH_ID = 'zz9/id/zz9'

MAX_WORKERS = 8
TIMEOUT = 25
RETRIES = 2
UNREACHABLE = '000'

CFN_LINT_PROVIDERS = 'cfnlint/data/schemas/providers/us-east-1.json'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn every 3xx into an HTTPError so its Location can be recorded."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url):
    """GET ``url`` without following redirects.

    Returns ``(status, location)`` as strings.  Connection-level failures are
    retried ``RETRIES`` times and then reported as ``('000', '')``.
    """
    request = urllib.request.Request(url, method='GET')
    for attempt in range(RETRIES + 1):
        try:
            with _OPENER.open(request, timeout=TIMEOUT) as response:
                return str(response.status), ''
        except urllib.error.HTTPError as error:
            location = error.headers.get('Location', '') or ''
            error.close()
            return str(error.code), normalize_location(url, location)
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            if attempt < RETRIES:
                time.sleep(1 + attempt)
    return UNREACHABLE, ''


def normalize_location(url, location):
    """Record a Location the way the committed snapshots do.

    The committed files hold curl's ``%{redirect_url}``: the Location made
    absolute against the request URL, with an empty trailing fragment
    (``...home#``) dropped.  Everything else is kept byte for byte.
    """
    if not location:
        return ''
    location = urllib.parse.urljoin(url, location)
    if location.endswith('#'):
        location = location[:-1]
    return location


def _q(value):
    return urllib.parse.quote(value, safe=':')


def _console(action, **params):
    query = '&'.join(f'{key}={_q(value)}' for key, value in params.items())
    return f'{CONSOLE_GO}{action}?{query}'


# Each probe is (url, record_redirect).  A snapshot row is the key columns
# followed by, per probe, its status and (when record_redirect) its Location.


def _services_probes(key):
    (name,) = key
    return [(_console('view', service=name, region=REGION), True)]


def _types_probes(key):
    (resource_type,) = key
    return [
        (_console('list', resourceType=resource_type, region=REGION), True),
        (_console('create', resourceType=resource_type, region=REGION), True),
    ]


def _view_samples_probes(key):
    kind, value = key
    if kind != 'arn':
        raise ValueError(f'view-samples: unknown kind {kind!r}')
    return [(_console('view', arn=value), True)]


def _view_by_id_probes(key):
    (resource_type,) = key
    return [
        (
            _console(
                'view',
                resourceType=resource_type,
                resourceId=resource_id,
                region=REGION,
            ),
            True,
        )
        for resource_id in (SENTINEL_ID, SENTINEL_SLASH_ID)
    ]


def _docs_probes(key):
    (name,) = key
    return [
        (f'{DOCS_HOST}{name}/', True),
        (f'{DOCS_HOST}cli/latest/reference/{name}/index.html', False),
    ]


def tier1_cli_names():
    from awscli.clidriver import create_clidriver

    return sorted(create_clidriver().subcommand_table)


def resource_types():
    with open(RESOURCE_TYPES_FILE, encoding='utf-8') as f:
        return sorted(line.strip() for line in f if line.strip())


def _committed_keys(name, key_columns):
    _, rows = read_snapshot(name)
    return [tuple(row[:key_columns]) for row in rows]


Spec = collections.namedtuple('Spec', 'columns key_columns probes keys')

SPECS = {
    'services': Spec(
        ('cli_service', 'http_status', 'redirect_url'),
        1,
        _services_probes,
        lambda: [(n,) for n in tier1_cli_names()],
    ),
    'types': Spec(
        (
            'resource_type',
            'list_status',
            'list_redirect',
            'create_status',
            'create_redirect',
        ),
        1,
        _types_probes,
        lambda: [(t,) for t in resource_types()],
    ),
    'view-samples': Spec(
        ('kind', 'input', 'http_status', 'redirect_url'),
        2,
        _view_samples_probes,
        lambda: _committed_keys('view-samples', 2),
    ),
    'view-by-id': Spec(
        (
            'resource_type',
            'id_status',
            'id_redirect',
            'slash_status',
            'slash_redirect',
        ),
        1,
        _view_by_id_probes,
        lambda: [(t,) for t in resource_types()],
    ),
    'docs': Spec(
        (
            'cli_service',
            'docs_landing_status',
            'docs_landing_redirect',
            'cli_reference_status',
        ),
        1,
        _docs_probes,
        lambda: [(n,) for n in tier1_cli_names()],
    ),
}


def snapshot_path(name):
    return os.path.join(SNAPSHOT_DIR, f'{name}.tsv')


def read_snapshot(name):
    """Return ``(header, rows)`` of a committed snapshot."""
    with open(snapshot_path(name), encoding='utf-8', newline='') as f:
        reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
        header = next(reader)
        rows = [row for row in reader if row]
    if tuple(header) != SPECS[name].columns:
        raise SystemExit(
            f'{name}: unexpected header {header!r}, '
            f'expected {list(SPECS[name].columns)!r}'
        )
    return header, rows


def _clean(value):
    # Keep the TSV well formed even if a header ever carries a tab/newline.
    return value.replace('\t', '%09').replace('\r', '%0D').replace('\n', '%0A')


def write_snapshot(name, rows):
    path = snapshot_path(name)
    fd, tmp = tempfile.mkstemp(dir=SNAPSHOT_DIR, suffix='.tsv.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(
            f,
            delimiter='\t',
            lineterminator='\n',
            quoting=csv.QUOTE_NONE,
            quotechar=None,
        )
        writer.writerow(SPECS[name].columns)
        for row in rows:
            writer.writerow([_clean(value) for value in row])
    os.replace(tmp, path)
    return path


def probe_row(spec, key):
    row = list(key)
    for url, record_redirect in spec.probes(key):
        status, location = fetch(url)
        row.append(status)
        if record_redirect:
            row.append(location)
    return row


def probe_rows(spec, keys, label):
    """Probe every key with a bounded thread pool, preserving key order."""
    rows = [None] * len(keys)
    with concurrent.futures.ThreadPoolExecutor(MAX_WORKERS) as pool:
        futures = {
            pool.submit(probe_row, spec, key): index
            for index, key in enumerate(keys)
        }
        for done, future in enumerate(
            concurrent.futures.as_completed(futures), 1
        ):
            rows[futures[future]] = future.result()
            if done % 250 == 0:
                print(f'{label}: {done}/{len(keys)}', file=sys.stderr)
    return rows


def _status_columns(spec):
    return [
        (index, column)
        for index, column in enumerate(spec.columns)
        if column.endswith('_status')
    ]


def histogram(spec, rows):
    parts = []
    for index, column in _status_columns(spec):
        counts = collections.Counter(row[index] for row in rows)
        body = ' '.join(f'{k}={v}' for k, v in sorted(counts.items()))
        parts.append(f'{column}[{body}]')
    return ' '.join(parts)


def capture(name):
    spec = SPECS[name]
    keys = spec.keys()
    rows = probe_rows(spec, keys, name)
    rows.sort(key=lambda row: row[0])  # stable: ties keep input order
    path = write_snapshot(name, rows)
    print(
        f'{name}: wrote {len(rows)} rows to '
        f'{os.path.relpath(path)}; {histogram(spec, rows)}'
    )
    return 0


def sample_indices(total, sample):
    """Every k-th row starting at 0; deterministic, no randomness."""
    count = min(sample, total)
    if count <= 0:
        return []
    step = total // count
    return [i * step for i in range(count)]


def check(name, sample):
    spec = SPECS[name]
    _, rows = read_snapshot(name)
    picked = [rows[i] for i in sample_indices(len(rows), sample)]
    keys = [tuple(row[: spec.key_columns]) for row in picked]
    live = probe_rows(spec, keys, name)
    differ = 0
    for committed, fresh in zip(picked, live):
        label = ' '.join(committed[: spec.key_columns])
        changes = [
            (column, old, new)
            for column, old, new in zip(spec.columns, committed, fresh)
            if old != new
        ]
        if not changes:
            print(f'= {name} {label}')
            continue
        differ += 1
        print(f'! {name} {label}')
        for column, old, new in changes:
            print(f'    {column}: {old!r} -> {new!r}')
    print(f'{name}: {len(picked)} sampled, {differ} differ')
    return differ


def _extract_types_from_wheel(wheel_path):
    with zipfile.ZipFile(wheel_path) as wheel:
        data = json.loads(wheel.read(CFN_LINT_PROVIDERS))
    return sorted(data)


def refresh_types(requirement):
    """Re-extract resource-types.txt from a downloaded cfn-lint wheel."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable,
                '-m',
                'pip',
                'download',
                '--no-deps',
                '--only-binary=:all:',
                '-d',
                tmp,
                requirement,
            ],
            check=True,
        )
        wheels = [f for f in os.listdir(tmp) if f.endswith('.whl')]
        if len(wheels) != 1:
            raise SystemExit(f'expected one wheel in {tmp}, got {wheels!r}')
        names = _extract_types_from_wheel(os.path.join(tmp, wheels[0]))
    old = (
        set(resource_types()) if os.path.exists(RESOURCE_TYPES_FILE) else set()
    )
    with open(RESOURCE_TYPES_FILE, 'w', encoding='utf-8', newline='') as f:
        f.writelines(f'{n}\n' for n in names)
    added = sorted(set(names) - old)
    removed = sorted(old - set(names))
    for n in added:
        print(f'+ {n}')
    for n in removed:
        print(f'- {n}')
    print(
        f'resource-types.txt: {len(names)} types from {wheels[0]} '
        f'({len(added)} added, {len(removed)} removed)'
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='snapshot-console-resolver',
        description=(
            'Capture or check the console go/ resolver and docs snapshots '
            'in scripts/console_db/snapshots/. Snapshot names: '
            + ', '.join(SPECS)
        ),
    )
    parser.add_argument(
        'words',
        nargs='*',
        metavar='[capture] NAME',
        help='"capture NAME..." re-captures; with --check, NAMEs to check '
        '(default: every committed snapshot)',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='compare a sample of committed rows with live answers',
    )
    parser.add_argument(
        '--sample',
        type=int,
        default=20,
        help='rows to re-request per snapshot with --check (default 20)',
    )
    parser.add_argument(
        '--refresh-types',
        nargs='?',
        const='cfn-lint',
        metavar='REQUIREMENT',
        help='rewrite resource-types.txt from a cfn-lint wheel '
        '(default requirement: cfn-lint)',
    )
    args = parser.parse_args(argv)

    if args.refresh_types is not None:
        if args.words or args.check:
            parser.error('--refresh-types takes no other arguments')
        return refresh_types(args.refresh_types)

    words = list(args.words)
    capturing = bool(words) and words[0] == 'capture'
    names = words[1:] if capturing else words
    unknown = [n for n in names if n not in SPECS]
    if unknown:
        parser.error(
            f'unknown snapshot(s) {unknown!r}; choose from {list(SPECS)}'
        )

    if args.check:
        if capturing:
            parser.error('use either --check or capture, not both')
        if args.sample < 1:
            parser.error('--sample must be at least 1')
        names = names or [n for n in SPECS if os.path.exists(snapshot_path(n))]
        differ = sum(check(name, args.sample) for name in names)
        return 1 if differ else 0

    if not capturing or not names:
        parser.error('nothing to do: use "capture NAME..." or --check')
    for name in names:
        capture(name)
    return 0
