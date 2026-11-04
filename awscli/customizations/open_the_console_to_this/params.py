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
"""Parse functions for curated intent params (contract section 1.2).

Each function receives the full list of values typed for one CLI argument
and returns a string, or None when the param is absent.  A bare flag gives
an empty list; ``present`` is the only function that returns a value for
it, every other function returns None for an empty list.
"""

import re
from urllib.parse import urlparse

S3_SCHEME = 's3://'


def first(values):
    return values[0] if values else None


def last(values):
    return values[-1] if values else None


def _is_s3_uri(value):
    return isinstance(value, str) and value.startswith(S3_SCHEME)


def _split_s3(value):
    """Split ``s3://b/k``, ``b/k`` or ``b`` into ``(bucket, key)``.

    Returns ``(None, None)`` when there is no bucket.
    """
    if not isinstance(value, str):
        return None, None
    if value.startswith(S3_SCHEME):
        value = value[len(S3_SCHEME) :]
    bucket, _, key = value.partition('/')
    if not bucket:
        return None, None
    return bucket, key


def _first_s3_value(values):
    """The first value that is an ``s3://`` URI, else the first value."""
    for value in values or ():
        if _is_s3_uri(value):
            return value
    return first(values)


def _target_value(values):
    """For cp/mv/sync: the last value when it is an S3 URI, else the first."""
    if values and _is_s3_uri(values[-1]):
        return values[-1]
    return first(values)


def _bucket(value):
    return _split_s3(value)[0]


def _key(value):
    key = _split_s3(value)[1]
    return key or None


def _prefix(value):
    key = _split_s3(value)[1]
    if not key or '/' not in key:
        return None
    return key[: key.rindex('/') + 1]


def _object(value):
    key = _split_s3(value)[1]
    if not key or key.endswith('/'):
        return None
    return key


def s3uri_bucket(values):
    return _bucket(_first_s3_value(values))


def s3uri_key(values):
    return _key(_first_s3_value(values))


def s3uri_prefix(values):
    return _prefix(_first_s3_value(values))


def s3uri_object(values):
    return _object(_first_s3_value(values))


def s3_target_bucket(values):
    return _bucket(_target_value(values))


def s3_target_key(values):
    return _key(_target_value(values))


def s3_target_prefix(values):
    return _prefix(_target_value(values))


def _arn_parts(value):
    """``arn:partition:service:region:account:resource`` -> 6 parts."""
    if not isinstance(value, str):
        return None
    parts = value.split(':', 5)
    if len(parts) != 6 or parts[0] != 'arn':
        return None
    return parts


def arn_resource(values):
    parts = _arn_parts(first(values))
    if parts is None:
        return None
    resource = parts[5]
    cut = [i for i in (resource.find('/'), resource.find(':')) if i >= 0]
    if cut:
        resource = resource[min(cut) + 1 :]
    return resource or None


def arn_account(values):
    parts = _arn_parts(first(values))
    return (parts[4] or None) if parts else None


def arn_region(values):
    parts = _arn_parts(first(values))
    return (parts[3] or None) if parts else None


def _queue_url_segments(values):
    value = first(values)
    if not isinstance(value, str):
        return []
    return [s for s in urlparse(value).path.split('/') if s]


def queue_url_name(values):
    segments = _queue_url_segments(values)
    return segments[-1] if segments else None


def queue_url_account(values):
    segments = _queue_url_segments(values)
    return segments[-2] if len(segments) >= 2 else None


def basename(values):
    value = first(values)
    if not isinstance(value, str):
        return None
    return value.rsplit('/', 1)[-1] or None


def present(values):
    """``'1'`` when the option was typed, even as a bare flag."""
    return None if values is None else '1'


def _first_str(values):
    value = first(values)
    return value if isinstance(value, str) else None


def is_arn(values):
    value = _first_str(values)
    parts = _arn_parts(value)
    if parts is None or not parts[1] or not parts[2]:
        return None
    return value


def _arn_resource_part(values):
    parts = _arn_parts(_first_str(values))
    return parts[5] if parts else None


def arn_type(values):
    resource = _arn_resource_part(values)
    if not resource:
        return None
    cut = [i for i in (resource.find('/'), resource.find(':')) if i >= 0]
    if not cut:
        return None
    return resource[: min(cut)] or None


def arn_name(values):
    resource = _arn_resource_part(values)
    if not resource:
        return None
    return re.split('[/:]', resource)[-1] or None


def before_colon(values):
    value = _first_str(values)
    return (value.partition(':')[0] or None) if value else None


def after_colon(values):
    value = _first_str(values)
    return (value.partition(':')[2] or None) if value else None


def before_dot(values):
    value = _first_str(values)
    return (value.partition('.')[0] or None) if value else None


def first_label(values):
    value = _first_str(values)
    if not value:
        return None
    if '://' in value:
        value = urlparse(value).hostname or ''
    return value.partition('.')[0] or None


def lower(values):
    value = _first_str(values)
    return (value.lower() or None) if value else None


def strip_leading_slash(values):
    value = _first_str(values)
    if not value:
        return None
    return (value[1:] if value.startswith('/') else value) or None


def ensure_trailing_slash(values):
    value = _first_str(values)
    if not value:
        return None
    return value if value.endswith('/') else value + '/'


def strip_wildcard_suffix(values):
    value = _first_str(values)
    if not value:
        return None
    return (value[:-2] if value.endswith(':*') else value) or None


_SECRET_SUFFIX = re.compile(r'-[A-Za-z0-9]{6}$')


def secret_name(values):
    """The secret name of a Secrets Manager ARN, or a plain name as is."""
    value = _first_str(values)
    if not value:
        return None
    parts = _arn_parts(value)
    if parts is None:
        return value
    resource = parts[5]
    if resource.startswith('secret:'):
        resource = resource[len('secret:') :]
    return _SECRET_SUFFIX.sub('', resource) or None


def _dir(value):
    key = _split_s3(value)[1]
    if not key:
        return None
    return key if key.endswith('/') else key + '/'


def s3uri_dir(values):
    return _dir(_first_s3_value(values))


def prefix_dir(values):
    value = _first_str(values)
    if not value or '/' not in value:
        return None
    return value[: value.rindex('/') + 1]


def s3_target_object(values):
    return _object(_target_value(values))


def filters_first_value(values):
    """The first ``Values=`` entry of ``Name=x,Values=a,b`` shorthand."""
    for value in values or ():
        if not isinstance(value, str) or 'Values=' not in value:
            continue
        entry = value.split('Values=', 1)[1].split(',', 1)[0]
        return entry.strip() or None
    return None


DEFAULT_PARSE = 'first'
PARSERS = {
    'first': first,
    'last': last,
    's3uri_bucket': s3uri_bucket,
    's3uri_key': s3uri_key,
    's3uri_prefix': s3uri_prefix,
    's3uri_object': s3uri_object,
    's3_target_bucket': s3_target_bucket,
    's3_target_key': s3_target_key,
    's3_target_prefix': s3_target_prefix,
    'arn_resource': arn_resource,
    'arn_account': arn_account,
    'arn_region': arn_region,
    'queue_url_name': queue_url_name,
    'queue_url_account': queue_url_account,
    'basename': basename,
    'present': present,
    'is_arn': is_arn,
    'arn_type': arn_type,
    'arn_name': arn_name,
    'before_colon': before_colon,
    'after_colon': after_colon,
    'before_dot': before_dot,
    'first_label': first_label,
    'lower': lower,
    'strip_leading_slash': strip_leading_slash,
    'ensure_trailing_slash': ensure_trailing_slash,
    'strip_wildcard_suffix': strip_wildcard_suffix,
    'secret_name': secret_name,
    's3uri_dir': s3uri_dir,
    'prefix_dir': prefix_dir,
    's3_target_object': s3_target_object,
    'filters_first_value': filters_first_value,
}


def parse_param(parse, values):
    """Apply the parse function named ``parse`` (None means ``first``).

    ``values`` is the list typed for the argument (empty for a bare
    flag); None means the argument was not typed at all.  An unknown name
    raises ``KeyError``; callers decide what that means.
    """
    func = PARSERS[parse or DEFAULT_PARSE]
    return func(None if values is None else list(values))
