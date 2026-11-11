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
"""Build an AWS console URL for a CLI command at runtime.

URL shapes follow the a9s consolelink helpers: the partition console
host, a regional or global console URL, and ``/go/view`` for an ARN
when no service page is known.
"""

import logging
import re
from urllib.parse import quote, quote_plus, urlparse

from botocore import xform_name

from awscli.customizations.open_the_console_to_this import args, params
from awscli.customizations.open_the_console_to_this import urls as _urls

LOG = logging.getLogger(__name__)

FALLBACK_SOURCE = 'fallback'
CONSOLE_SOURCE = 'console'
GO_VIEW_SOURCE = 'go-view'

# Hosts Valid accepts, as an exact match or as the suffix of a subdomain.
# The same three hosts as a9s consolelink.Domain.
CONSOLE_HOSTS = (
    'console.aws.amazon.com',
    'console.amazonaws-us-gov.com',
    'console.amazonaws.cn',
)

_CLI_ONLY = frozenset(['configure', 'history'])
_MODEL_NAMES = {'s3api': 's3'}
_REFERENCE_ONLY = _CLI_ONLY

_S3_COMMANDS = frozenset(
    ['cp', 'ls', 'mb', 'mv', 'presign', 'rb', 'rm', 'sync', 'website']
)
_S3_FLAGS = frozenset(
    [
        'case-conflict',
        'dryrun',
        'follow-symlinks',
        'force',
        'force-glacier-transfer',
        'human-readable',
        'ignore-glacier-warnings',
        'no-follow-symlinks',
        'no-guess-mime-type',
        'no-overwrite',
        'no-progress',
        'only-show-errors',
        'progress-multiline',
        'quiet',
        'recursive',
        'summarize',
        'validate-same-s3-paths',
    ]
)
_S3_POSITIONAL = {
    'cp': ['paths'],
    'ls': ['paths'],
    'mb': ['path'],
    'mv': ['paths'],
    'presign': ['path'],
    'rb': ['path'],
    'rm': ['paths'],
    'sync': ['paths'],
    'website': ['paths'],
}
# List options the console page reads. The service model adds the rest
# when a session can load it.
_MULTI_OPTIONS = frozenset(
    [
        'group-ids',
        'image-ids',
        'instance-ids',
        'network-interface-ids',
        'repository-names',
        'snapshot-ids',
        'subnet-ids',
        'volume-ids',
        'vpc-ids',
    ]
)

_INSTANCE = re.compile(r'^i-[0-9a-f]+$')
_VOLUME = re.compile(r'^vol-[0-9a-f]+$')
_IMAGE = re.compile(r'^ami-[0-9a-f]+$')
_SECURITY_GROUP = re.compile(r'^sg-[0-9a-f]+$')
_VPC = re.compile(r'^vpc-[0-9a-f]+$')
_SUBNET = re.compile(r'^subnet-[0-9a-f]+$')

_LAMBDA_OPS = frozenset(
    [
        'create-function',
        'delete-function',
        'get-function',
        'get-function-configuration',
        'invoke',
        'list-functions',
        'publish-version',
        'update-function-code',
        'update-function-configuration',
    ]
)
_TABLE_OPS = frozenset(
    [
        'create-table',
        'delete-table',
        'describe-table',
        'list-tables',
        'update-table',
    ]
)
_ROLE_OPS = frozenset(
    ['create-role', 'delete-role', 'get-role', 'list-roles', 'update-role']
)
_USER_OPS = frozenset(
    ['create-user', 'delete-user', 'get-user', 'list-users']
)
_QUEUE_OPS = frozenset(
    [
        'create-queue',
        'delete-queue',
        'get-queue-attributes',
        'get-queue-url',
        'list-queues',
        'purge-queue',
        'set-queue-attributes',
    ]
)
_STACK_OPS = frozenset(
    [
        'create-stack',
        'delete-stack',
        'describe-stacks',
        'list-stacks',
        'update-stack',
    ]
)

SKIPPED_KEYS = frozenset(['ResponseMetadata'])
_SPEC_CACHE = {}


class Context:
    """Where the console is: region, partition and a lazy account id."""

    def __init__(self, region, partition, account_id=None, session=None):
        self.region = region
        self.partition = partition
        self.session = session
        func = account_id if account_id is not None else _none
        self._account = _LazyAccount(func)

    def account(self):
        """Return the account id, calling the supplied callable once."""
        return self._account.get()

    def __repr__(self):
        return (
            f'Context(region={self.region!r}, '
            f'partition={self.partition!r})'
        )


def _none():
    return None


class _LazyAccount:
    """Call the account callable at most once."""

    def __init__(self, func):
        self._func = func
        self._called = False
        self._value = None

    def get(self):
        if not self._called:
            self._called = True
            try:
                value = self._func()
            except Exception:
                LOG.debug('Account id lookup failed', exc_info=True)
                value = None
            self._value = str(value) if value else None
        return self._value


class Decision:
    """The URL chosen for a command and why."""

    __slots__ = ('url', 'node_path', 'source', 'verb', 'params', 'explanation')

    def __init__(self, url, node_path, source, verb, params, explanation):
        self.url = url
        self.node_path = node_path
        self.source = source
        self.verb = verb
        self.params = params
        self.explanation = explanation

    def _fields(self):
        return tuple(getattr(self, name) for name in self.__slots__)

    def __eq__(self, other):
        if not isinstance(other, Decision):
            return NotImplemented
        return self._fields() == other._fields()

    def __repr__(self):
        inner = ', '.join(
            f'{name}={getattr(self, name)!r}' for name in self.__slots__
        )
        return f'Decision({inner})'


class Command:
    """A service, an operation and the arguments after them."""

    def __init__(self, service, operation, parsed):
        self.service = service
        self.operation = operation
        self.options = parsed.options
        self.positionals = parsed.positionals
        self.positional_values = parsed.positional_values
        self.help = parsed.help

    def __repr__(self):
        return (
            f'Command(service={self.service!r}, '
            f'operation={self.operation!r}, help={self.help!r})'
        )


def domain_for_region(region):
    """Partition console host for ``region``.

    GovCloud regions use ``console.amazonaws-us-gov.com``, China
    regions use ``console.amazonaws.cn``, and every other region uses
    ``console.aws.amazon.com``.
    """
    region = region or ''
    if region.startswith('us-gov-'):
        return 'console.amazonaws-us-gov.com'
    if region.startswith('cn-'):
        return 'console.amazonaws.cn'
    return 'console.aws.amazon.com'


def _host(region, partition):
    if partition:
        return _urls.console_host(partition)
    return domain_for_region(region)


def regional(region, tail, partition=None):
    """Region-subdomain console URL. ``tail`` has no leading slash."""
    tail = (tail or '').lstrip('/')
    return f'https://{region}.{_host(region, partition)}/{tail}'


def global_url(region, tail, partition=None):
    """Partition console URL with no region subdomain."""
    tail = (tail or '').lstrip('/')
    return f'https://{_host(region, partition)}/{tail}'


def go_view(region, arn, partition=None):
    """Console URL for ``arn`` via AWS's ``/go/view`` resolver."""
    return global_url(
        region, 'go/view?arn=' + quote_plus(arn), partition
    )


def go_view_service(region, service, partition=None):
    """Console URL for a service name via ``/go/view``."""
    tail = 'go/view?service=' + quote_plus(service) + '&region=' + quote_plus(
        region
    )
    return global_url(region, tail, partition)


def account_from_arn(ref):
    """Account id in ``ref``, or ``''`` when ``ref`` is not an ARN."""
    parts = _arn_fields(ref)
    if parts is None:
        return ''
    return parts[4]


def valid(url):
    """True when ``url`` is an https console URL on a known host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc
    if (
        parsed.scheme != 'https'
        or not host
        or host.startswith('.')
        or parsed.hostname is None
    ):
        return False
    name = parsed.hostname
    for console_host in CONSOLE_HOSTS:
        if name == console_host or name.endswith('.' + console_host):
            return True
    return False


def _arn_fields(ref):
    if not isinstance(ref, str) or not ref.startswith('arn:'):
        return None
    parts = ref.split(':', 5)
    if len(parts) != 6 or not parts[1] or not parts[2]:
        return None
    return parts


def _is_arn(value):
    return _arn_fields(value) is not None


def _arn_service(arn):
    parts = _arn_fields(arn)
    return parts[2] if parts else ''


def is_help(command, remaining, session=None):
    """True when the command asks for help rather than a console page."""
    if command == 'help':
        return True
    try:
        return parse_command(command, remaining, session).help
    except Exception:
        LOG.debug('Could not parse %r for help', command, exc_info=True)
        return False


def operation_known(session, service, operation):
    """True when ``operation`` is a command of ``service``.

    True when the service model cannot be read, so a missing session
    does not hide a command that was typed.
    """
    if service == 's3':
        return operation in _S3_COMMANDS
    if operation == 'wait':
        return True
    model = _service_model(session, service)
    if model is None:
        return True
    return any(
        xform_name(name, '-') == operation for name in model.operation_names
    )


def parse_command(service, remaining, session=None):
    """Parse ``aws <service> <remaining...>`` into a :class:`Command`."""
    remaining = list(remaining or ())
    operation = None
    rest = remaining
    if remaining and not remaining[0].startswith('-'):
        if remaining[0] == 'help':
            parsed = args.parse_remaining((), ())
            parsed.help = True
            return Command(service, None, parsed)
        operation = remaining[0]
        rest = remaining[1:]
    flags, scalars, positional = _syntax(service, operation, rest, session)
    parsed = args.parse_remaining(
        rest, positional, flags=flags, scalars=scalars
    )
    return Command(service, operation, parsed)


def resolve(command, remaining, ctx, response=None, after_run=False):
    """Return the :class:`Decision` for ``aws <command> <remaining...>``."""
    try:
        return _resolve(command, remaining, ctx, response, after_run)
    except Exception:
        LOG.debug('Unexpected error resolving %r', command, exc_info=True)
        return _console_home(
            ctx,
            _path(command),
            'No console page could be built, so the console home '
            'page was used.',
        )


def _resolve(command, remaining, ctx, response, after_run):
    if command in _CLI_ONLY or command == 'help':
        return _console_home(
            ctx,
            _path(command, _operation_name(remaining)),
            f'{command} is a CLI command, so the console home page '
            'was used.',
        )
    parsed = parse_command(command, remaining, ctx.session)
    builder = _BUILDERS.get(command)
    if builder is not None:
        decision = builder(parsed, ctx, response, after_run)
        if decision is not None and valid(decision.url):
            return decision
    arn = _one_arn(command, parsed, response)
    if arn:
        url = go_view(ctx.region, arn, ctx.partition)
        return _make(
            url,
            _path(command, parsed.operation),
            GO_VIEW_SOURCE,
            'view',
            {'arn': arn},
            'An ARN was given, so the console go/view page was used.',
        )
    if command in _HOMES:
        return _HOMES[command](parsed, ctx)
    return _make(
        go_view_service(ctx.region, command, ctx.partition),
        _path(command, parsed.operation),
        FALLBACK_SOURCE,
        'home',
        {},
        f'{command!r} has no console page, so go/view?service= was used.',
    )


def _operation_name(remaining):
    remaining = list(remaining or ())
    if not remaining:
        return None
    token = remaining[0]
    if token.startswith('-') or token == 'help':
        return None
    return token


def _path(service, operation=None):
    if not service:
        return 'aws'
    if operation:
        return f'aws.{service}.{operation}'
    return f'aws.{service}'


def _make(url, path, source, verb, params_used, explanation):
    return Decision(url, path, source, verb, params_used, explanation)


def _console_home(ctx, path, explanation):
    host = _urls.console_host(ctx.partition)
    return _make(
        _urls.console_home(host, ctx.region),
        path,
        FALLBACK_SOURCE,
        'home',
        {},
        explanation,
    )


def _region_query(ctx):
    return quote(ctx.region, safe='')


def _regional_page(ctx, slug, fragment=None):
    tail = f'{slug}?region={_region_query(ctx)}'
    if fragment:
        tail += '#' + fragment
    return regional(ctx.region, tail, ctx.partition)


def _quote_id(value):
    return quote(value, safe='')


# --- argument shapes -------------------------------------------------------


def _syntax(service, operation, tokens, session):
    flags, multi = _model_spec(session, service, operation)
    if service == 's3':
        flags = set(flags) | set(_S3_FLAGS)
    else:
        flags = set(flags)
    multi = set(multi) | (set(_option_names(tokens)) & set(_MULTI_OPTIONS))
    scalars = [
        name
        for name in _option_names(tokens)
        if name not in flags and name not in multi
    ]
    positional = _S3_POSITIONAL.get(operation, ()) if service == 's3' else ()
    return flags, scalars, positional


def _option_names(tokens):
    names = []
    for token in tokens:
        if token.startswith('--') and token != '--':
            names.append(token[2:].partition('=')[0])
    return names


def _service_model(session, service):
    if session is None or not hasattr(session, 'get_service_model'):
        return None
    try:
        name = _MODEL_NAMES.get(service, service)
        return session.get_service_model(name)
    except Exception:
        LOG.debug('Could not read the service model for %s', service)
        return None


def _model_spec(session, service, operation):
    """Return ``(flags, multi-value option names)`` for an operation."""
    if not operation:
        return frozenset(), frozenset()
    key = (service, operation)
    cached = _SPEC_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        spec = _load_model_spec(session, service, operation)
    except Exception:
        LOG.debug(
            'Could not read arguments for %s %s',
            service,
            operation,
            exc_info=True,
        )
        return frozenset(), frozenset()
    if spec is None:
        return frozenset(), frozenset()
    _SPEC_CACHE[key] = spec
    return spec


def _load_model_spec(session, service, operation):
    model = _service_model(session, service)
    if model is None:
        return None
    operation_model = None
    for name in model.operation_names:
        if xform_name(name, '-') == operation:
            operation_model = model.operation_model(name)
            break
    shape = getattr(operation_model, 'input_shape', None)
    members = getattr(shape, 'members', None)
    if not isinstance(members, dict):
        # No input, or not a real service model. Do not cache the latter:
        # a stand-in session must not hide a later real one.
        if operation_model is None or shape is None:
            return frozenset(), frozenset()
        return None
    flags = []
    multi = []
    for name, member in members.items():
        cli_name = xform_name(name, '-')
        kind = getattr(member, 'type_name', None)
        if kind == 'boolean':
            flags.append(cli_name)
        elif kind in ('list', 'map'):
            multi.append(cli_name)
    return frozenset(flags), frozenset(multi)


def values_for(parsed, response, *names):
    """Option values, then matching strings from ``response``, in order."""
    found = []
    for name in names:
        found.extend(parsed.options.get(name) or ())
        found.extend(parsed.positional_values.get(name) or ())
        if response is not None:
            found.extend(find_values(response, name))
    out = []
    for value in found:
        if (
            isinstance(value, str)
            and value
            and not value.startswith('--')
            and value not in out
        ):
            out.append(value)
    return out


def find_values(response, option_name):
    """String values of the response key that matches ``option_name``."""
    if response is None:
        return []
    wanted = _normalize(option_name)
    keys = [wanted]
    if wanted.endswith('s'):
        keys.append(wanted[:-1])
    for key in keys:
        values = _search(response, key)
        if values:
            return values
    return []


def _normalize(name):
    return name.replace('-', '').replace('_', '').lower()


def _search(response, key):
    level = [response]
    while level:
        found = []
        deeper = []
        for item in _flatten(level):
            for name, value in item.items():
                if name in SKIPPED_KEYS:
                    continue
                if _normalize(name) == key:
                    found.extend(_strings(value))
                elif isinstance(value, (dict, list)):
                    deeper.append(value)
        if found:
            return list(dict.fromkeys(found))
        level = deeper
    return []


def _flatten(items):
    """Yield the dicts of ``items``, descending into lists."""
    stack = list(reversed(items))
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            stack.extend(reversed(item))


def _strings(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    return []


def _one_arn(service, parsed, response):
    typed = []
    pools = list(parsed.options.values()) + [parsed.positionals]
    for values in pools:
        typed.extend(value for value in values if _is_arn(value))
    typed = list(dict.fromkeys(typed))
    if typed:
        matched = [
            arn
            for arn in typed
            if _arn_service(arn) == _MODEL_NAMES.get(service, service)
        ]
        chosen = matched or typed
        return chosen[0] if len(chosen) == 1 else None
    if response is None:
        return None
    found = _arns_in_response(response)
    want = _MODEL_NAMES.get(service, service)
    matched = [arn for arn in found if _arn_service(arn) == want]
    if len(matched) == 1:
        return matched[0]
    return None


def _arns_in_response(response):
    """ARN strings in ``response``, ignoring response metadata."""
    found = []
    level = [response]
    while level:
        deeper = []
        for item in _flatten(level):
            for name, value in item.items():
                if name in SKIPPED_KEYS:
                    continue
                for entry in _strings(value):
                    if _is_arn(entry) and entry not in found:
                        found.append(entry)
                if isinstance(value, (dict, list)):
                    deeper.append(value)
        level = deeper
    return found


def _arn_only(values):
    return bool(values) and all(_is_arn(value) for value in values)


# --- service pages ---------------------------------------------------------


def _page(ctx, parsed, url, verb, used, detail):
    return _make(
        url,
        _path(parsed.service, parsed.operation),
        CONSOLE_SOURCE,
        verb,
        used,
        f'{_path(parsed.service, parsed.operation)}: {detail}.',
    )


def _s3_buckets(ctx, parsed):
    url = global_url(
        ctx.region,
        f's3/buckets?region={_region_query(ctx)}',
        ctx.partition,
    )
    return _page(ctx, parsed, url, 'list', {}, 'opened the bucket list')


def _s3_bucket(ctx, parsed, bucket, prefix=None, tab=None):
    tail = f's3/buckets/{_quote_id(bucket)}?region={_region_query(ctx)}'
    used = {'bucket': bucket}
    if prefix:
        tail += '&prefix=' + quote_plus(prefix) + '&showversions=false'
        used['prefix'] = prefix
    if tab:
        tail += '&tab=' + quote(tab, safe='')
        used['tab'] = tab
    url = global_url(ctx.region, tail, ctx.partition)
    return _page(ctx, parsed, url, 'view', used, f'opened bucket {bucket}')


def _s3_object(ctx, parsed, bucket, key):
    tail = (
        f's3/object/{_quote_id(bucket)}?region={_region_query(ctx)}'
        f'&prefix={quote_plus(key)}'
    )
    url = global_url(ctx.region, tail, ctx.partition)
    return _page(
        ctx,
        parsed,
        url,
        'view',
        {'bucket': bucket, 'key': key},
        f'opened object {key} in bucket {bucket}',
    )


def _s3_paths(parsed):
    for name in ('paths', 'path'):
        values = parsed.positional_values.get(name)
        if values:
            return list(values)
    return list(parsed.positionals)


def _s3_choice(ctx, parsed, bucket, prefix, key, recursive, tab=None):
    if bucket and recursive and prefix:
        return _s3_bucket(ctx, parsed, bucket, prefix)
    if bucket and recursive:
        return _s3_bucket(ctx, parsed, bucket)
    if bucket and key and not recursive:
        return _s3_object(ctx, parsed, bucket, key)
    if bucket and prefix:
        return _s3_bucket(ctx, parsed, bucket, prefix)
    if bucket and tab:
        return _s3_bucket(ctx, parsed, bucket, tab=tab)
    if bucket:
        return _s3_bucket(ctx, parsed, bucket)
    return _s3_buckets(ctx, parsed)


def _build_s3(parsed, ctx, response, after_run):
    del response, after_run
    operation = parsed.operation
    if operation not in _S3_COMMANDS:
        return _s3_buckets(ctx, parsed)
    paths = _s3_paths(parsed)
    recursive = 'recursive' in parsed.options
    key = None
    tab = None
    if operation in ('cp', 'mv'):
        bucket = params.s3_target_bucket(paths)
        prefix = params.s3_target_prefix(paths)
        if not recursive:
            key = params.s3_target_object(paths)
    elif operation == 'sync':
        bucket = params.s3_target_bucket(paths)
        prefix = params.s3_target_prefix(paths)
    elif operation == 'rm':
        bucket = params.s3uri_bucket(paths)
        prefix = params.s3uri_prefix(paths)
        if recursive:
            prefix = params.s3uri_dir(paths) or prefix
        else:
            key = params.s3uri_object(paths)
    elif operation == 'presign':
        bucket = params.s3uri_bucket(paths)
        key = params.s3uri_object(paths)
        prefix = None
        recursive = False
    elif operation == 'website':
        bucket = params.s3uri_bucket(paths)
        prefix = None
        tab = 'properties'
        recursive = False
    else:
        bucket = params.s3uri_bucket(paths)
        prefix = params.s3uri_prefix(paths)
        recursive = False
    return _s3_choice(ctx, parsed, bucket, prefix, key, recursive, tab)


def _first_plain(parsed, response, *names):
    values = [value for value in values_for(parsed, response, *names)]
    if _arn_only(values):
        return None, True
    plain = [value for value in values if not _is_arn(value)]
    return (plain[0] if plain else None), False


def _build_s3api(parsed, ctx, response, after_run):
    del after_run
    bucket, bucket_arn = _first_plain(parsed, response, 'bucket')
    key, key_arn = _first_plain(parsed, response, 'key')
    prefix, _prefix_arn = _first_plain(parsed, response, 'prefix')
    if (bucket_arn or key_arn) and not bucket and not key:
        return None
    return _s3_choice(ctx, parsed, bucket, prefix, key, False)


def _ec2_fragment(ctx, parsed, fragment, verb, used, detail):
    url = _regional_page(ctx, 'ec2/home', fragment)
    return _page(ctx, parsed, url, verb, used, detail)


def _vpc_fragment(ctx, parsed, fragment, verb, used, detail):
    url = _regional_page(ctx, 'vpc/home', fragment)
    return _page(ctx, parsed, url, verb, used, detail)


def _id_page(ctx, parsed, response, names, pattern, one, many, ops, vpc=False):
    raw = values_for(parsed, response, *names)
    ids = [value for value in raw if pattern.match(value)]
    page = _vpc_fragment if vpc else _ec2_fragment
    if len(ids) == 1:
        fragment = one.format(id=_quote_id(ids[0]))
        return page(
            ctx,
            parsed,
            fragment,
            'view',
            {names[0]: ids[0]},
            f'opened {ids[0]}',
        )
    if len(ids) > 1:
        return page(
            ctx,
            parsed,
            many,
            'list',
            {names[0]: ids},
            'opened the list for several ids',
        )
    if _arn_only(raw):
        return None
    if parsed.operation in ops:
        return page(ctx, parsed, many, 'list', {}, 'opened the list')
    return None


def _build_ec2(parsed, ctx, response, after_run):
    pages = (
        _id_page(
            ctx,
            parsed,
            response,
            ('instance-ids', 'instance-id'),
            _INSTANCE,
            'InstanceDetails:instanceId={id}',
            'Instances:',
            frozenset(
                [
                    'describe-instances',
                    'reboot-instances',
                    'start-instances',
                    'stop-instances',
                    'terminate-instances',
                ]
            ),
        ),
        _run_instances(parsed, ctx, response, after_run),
        _id_page(
            ctx,
            parsed,
            response,
            ('volume-ids', 'volume-id'),
            _VOLUME,
            'VolumeDetails:volumeId={id}',
            'Volumes:',
            frozenset(['describe-volumes']),
        ),
        _id_page(
            ctx,
            parsed,
            response,
            ('image-ids', 'image-id'),
            _IMAGE,
            'ImageDetails:imageId={id}',
            None,
            frozenset(['describe-images']),
        ),
        _id_page(
            ctx,
            parsed,
            response,
            ('group-ids', 'group-id'),
            _SECURITY_GROUP,
            'SecurityGroup:groupId={id}',
            'SecurityGroups:',
            frozenset(['describe-security-groups']),
            vpc=True,
        ),
        _id_page(
            ctx,
            parsed,
            response,
            ('vpc-ids', 'vpc-id'),
            _VPC,
            'VpcDetails:VpcId={id}',
            'vpcs:',
            frozenset(['describe-vpcs']),
            vpc=True,
        ),
        _id_page(
            ctx,
            parsed,
            response,
            ('subnet-ids', 'subnet-id'),
            _SUBNET,
            'SubnetDetails:subnetId={id}',
            'subnets:',
            frozenset(['describe-subnets']),
            vpc=True,
        ),
    )
    for decision in pages:
        if decision is not None:
            return decision
    if parsed.operation is None:
        return _ec2_home(parsed, ctx)
    return None


def _run_instances(parsed, ctx, response, after_run):
    if parsed.operation != 'run-instances':
        return None
    raw = values_for(parsed, response, 'instance-ids', 'instance-id')
    ids = [value for value in raw if _INSTANCE.match(value)]
    if len(ids) == 1:
        fragment = 'InstanceDetails:instanceId=' + _quote_id(ids[0])
        return _ec2_fragment(
            ctx,
            parsed,
            fragment,
            'view',
            {'instance-id': ids[0]},
            f'opened {ids[0]}',
        )
    if len(ids) > 1 or after_run:
        return _ec2_fragment(
            ctx, parsed, 'Instances:', 'list', {}, 'opened the instance list'
        )
    if _arn_only(raw):
        return None
    return _ec2_fragment(
        ctx,
        parsed,
        'LaunchInstances:',
        'create',
        {},
        'opened the launch page',
    )


def _ec2_home(parsed, ctx):
    return _page(
        ctx,
        parsed,
        _regional_page(ctx, 'ec2/home'),
        'home',
        {},
        'opened the EC2 home page',
    )


def _build_lambda(parsed, ctx, response, after_run):
    raw = values_for(parsed, response, 'function-name')
    if _arn_only(raw):
        return None
    names = [value for value in raw if not _is_arn(value)]
    if len(names) == 1:
        fragment = '/functions/' + _quote_id(names[0])
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'lambda/home', fragment),
            'view',
            {'function-name': names[0]},
            f'opened function {names[0]}',
        )
    if len(names) > 1 or parsed.operation in _LAMBDA_OPS:
        creating = parsed.operation == 'create-function' and not names
        creating = creating and not after_run
        if creating:
            fragment = '/create/function'
            verb = 'create'
            detail = 'opened the create function page'
        else:
            fragment = '/functions'
            verb = 'list'
            detail = 'opened the function list'
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'lambda/home', fragment),
            verb,
            {},
            detail,
        )
    if parsed.operation is None:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'lambda/home', '/begin'),
            'home',
            {},
            'opened the Lambda home page',
        )
    return None


def _build_dynamodb(parsed, ctx, response, after_run):
    raw = values_for(parsed, response, 'table-name')
    if _arn_only(raw):
        return None
    names = [value for value in raw if not _is_arn(value)]
    if len(names) == 1:
        fragment = 'table?name=' + _quote_id(names[0])
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'dynamodbv2/home', fragment),
            'view',
            {'table-name': names[0]},
            f'opened table {names[0]}',
        )
    if parsed.operation == 'create-table' and not names and not after_run:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'dynamodbv2/home', 'create-table'),
            'create',
            {},
            'opened the create table page',
        )
    if parsed.operation in _TABLE_OPS:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'dynamodbv2/home', 'table'),
            'list',
            {},
            'opened the table list',
        )
    if parsed.operation is None:
        return _dynamodb_home(parsed, ctx)
    return None


def _dynamodb_home(parsed, ctx):
    return _page(
        ctx,
        parsed,
        _regional_page(ctx, 'dynamodbv2/home'),
        'home',
        {},
        'opened the DynamoDB home page',
    )


def _build_iam(parsed, ctx, response, after_run):
    del after_run
    role, role_arn = _first_plain(parsed, response, 'role-name')
    user, user_arn = _first_plain(parsed, response, 'user-name')
    if role_arn or user_arn:
        return None
    if role and parsed.operation not in _USER_OPS:
        fragment = '/roles/details/' + _quote_id(role)
        return _iam_page(
            ctx,
            parsed,
            fragment,
            'view',
            {'role-name': role},
            f'opened role {role}',
        )
    if user:
        fragment = '/users/details/' + _quote_id(user)
        return _iam_page(
            ctx,
            parsed,
            fragment,
            'view',
            {'user-name': user},
            f'opened user {user}',
        )
    if parsed.operation in _ROLE_OPS:
        return _iam_page(
            ctx, parsed, '/roles', 'list', {}, 'opened the role list'
        )
    if parsed.operation in _USER_OPS:
        return _iam_page(
            ctx, parsed, '/users', 'list', {}, 'opened the user list'
        )
    if parsed.operation is None:
        return _iam_home(parsed, ctx)
    return None


def _iam_page(ctx, parsed, fragment, verb, used, detail):
    url = global_url(ctx.region, 'iam/home#' + fragment, ctx.partition)
    return _page(ctx, parsed, url, verb, used, detail)


def _iam_home(parsed, ctx):
    url = global_url(ctx.region, 'iam/home', ctx.partition)
    return _page(ctx, parsed, url, 'home', {}, 'opened the IAM home page')


def _build_sqs(parsed, ctx, response, after_run):
    raw = values_for(parsed, response, 'queue-url')
    urls = [
        value
        for value in raw
        if value.startswith('https://') or value.startswith('http://')
    ]
    if len(urls) == 1:
        fragment = '/queues/' + _quote_id(urls[0])
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'sqs/v3/home', fragment),
            'view',
            {'queue-url': urls[0]},
            'opened the queue',
        )
    if _arn_only(raw):
        return None
    if parsed.operation == 'create-queue' and not urls and not after_run:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'sqs/v3/home', '/create-queue'),
            'create',
            {},
            'opened the create queue page',
        )
    if parsed.operation in _QUEUE_OPS or parsed.operation is None:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'sqs/v3/home', '/queues'),
            'list',
            {},
            'opened the queue list',
        )
    return None


def _build_cloudformation(parsed, ctx, response, after_run):
    raw = values_for(parsed, response, 'stack-name')
    if _arn_only(raw):
        return None
    names = [value for value in raw if not _is_arn(value)]
    if len(names) == 1:
        fragment = 'stacks/stackinfo?stackId=' + _quote_id(names[0])
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudformation/home', fragment),
            'view',
            {'stack-name': names[0]},
            f'opened stack {names[0]}',
        )
    if parsed.operation == 'create-stack' and not names and not after_run:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudformation/home', 'stacks/create'),
            'create',
            {},
            'opened the create stack page',
        )
    if parsed.operation in _STACK_OPS:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudformation/home', 'stacks'),
            'list',
            {},
            'opened the stack list',
        )
    if parsed.operation is None:
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudformation/home'),
            'home',
            {},
            'opened the CloudFormation home page',
        )
    return None


def _build_logs(parsed, ctx, response, after_run):
    del after_run
    group, group_arn = _log_group(parsed, response)
    stream, stream_arn = _first_plain(parsed, response, 'log-stream-name')
    if (group_arn or stream_arn) and not group:
        return None
    if group and stream:
        fragment = (
            'logsV2:log-groups/log-group/'
            + _quote_id(group)
            + '/log-events/'
            + _quote_id(stream)
        )
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudwatch/home', fragment),
            'view',
            {'log-group-name': group, 'log-stream-name': stream},
            f'opened log stream {stream}',
        )
    if group:
        fragment = 'logsV2:log-groups/log-group/' + _quote_id(group)
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudwatch/home', fragment),
            'view',
            {'log-group-name': group},
            f'opened log group {group}',
        )
    if parsed.operation is None or parsed.operation.startswith(
        ('describe-log', 'get-log', 'filter-log', 'list-')
    ):
        return _page(
            ctx,
            parsed,
            _regional_page(ctx, 'cloudwatch/home'),
            'list',
            {},
            'opened CloudWatch Logs',
        )
    return None


def _log_group(parsed, response):
    name, name_arn = _first_plain(parsed, response, 'log-group-name')
    if name:
        return name, False
    ident, ident_arn = _first_plain(parsed, response, 'log-group-identifier')
    if ident_arn or name_arn:
        return None, True
    if ident and _is_arn(ident):
        resource = params.arn_resource([ident])
        return resource, False
    return ident, False


_BUILDERS = {
    'cloudformation': _build_cloudformation,
    'dynamodb': _build_dynamodb,
    'ec2': _build_ec2,
    'iam': _build_iam,
    'lambda': _build_lambda,
    'logs': _build_logs,
    's3': _build_s3,
    's3api': _build_s3api,
    'sqs': _build_sqs,
}


def _home_ec2(parsed, ctx):
    return _ec2_home(parsed, ctx)


def _home_lambda(parsed, ctx):
    return _page(
        ctx,
        parsed,
        _regional_page(ctx, 'lambda/home', '/begin'),
        'home',
        {},
        'opened the Lambda home page',
    )


def _home_logs(parsed, ctx):
    return _page(
        ctx,
        parsed,
        _regional_page(ctx, 'cloudwatch/home'),
        'home',
        {},
        'opened CloudWatch Logs',
    )


_HOMES = {
    'cloudformation': lambda parsed, ctx: _page(
        ctx,
        parsed,
        _regional_page(ctx, 'cloudformation/home'),
        'home',
        {},
        'opened the CloudFormation home page',
    ),
    'dynamodb': _dynamodb_home,
    'ec2': _home_ec2,
    'iam': _iam_home,
    'lambda': _home_lambda,
    'logs': _home_logs,
    's3': lambda parsed, ctx: _s3_buckets(ctx, parsed),
    's3api': lambda parsed, ctx: _s3_buckets(ctx, parsed),
    'sqs': lambda parsed, ctx: _page(
        ctx,
        parsed,
        _regional_page(ctx, 'sqs/v3/home', '/queues'),
        'list',
        {},
        'opened the queue list',
    ),
}
