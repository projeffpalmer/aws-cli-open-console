# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
"""Read buckets, keys and ARN resources from command arguments."""

S3_SCHEME = 's3://'


def first(values):
    return values[0] if values else None


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


def _dir(value):
    key = _split_s3(value)[1]
    if not key:
        return None
    return key if key.endswith('/') else key + '/'


def s3uri_bucket(values):
    return _bucket(_first_s3_value(values))


def s3uri_prefix(values):
    return _prefix(_first_s3_value(values))


def s3uri_object(values):
    return _object(_first_s3_value(values))


def s3uri_dir(values):
    return _dir(_first_s3_value(values))


def s3_target_bucket(values):
    return _bucket(_target_value(values))


def s3_target_prefix(values):
    return _prefix(_target_value(values))


def s3_target_object(values):
    return _object(_target_value(values))


def s3_target_dir(values):
    return _dir(_target_value(values))


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
