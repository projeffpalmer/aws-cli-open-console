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
from awscli.customizations.open_the_console_to_this import params
from awscli.testutils import unittest

KMS_KEY = (
    'arn:aws:kms:us-west-2:111122223333:key/'
    '1234abcd-12ab-34cd-56ef-1234567890ab'
)
KMS_ALIAS = 'arn:aws:kms:us-west-2:111122223333:alias/my-alias'
ROLE = 'arn:aws:iam::111122223333:role/service-role/MyRole'
TOPIC = 'arn:aws:sns:us-west-2:111122223333:my-topic'
SECRET = 'arn:aws:secretsmanager:us-west-2:111122223333:secret:prod/db-AbCdEf'
LOG_GROUP = 'arn:aws:logs:us-west-2:111122223333:log-group:/aws/lambda/f:*'

# Every function added for curated params, with the result for an empty
# value list (a bare flag).
NEW_FUNCTIONS = [
    'present',
    'is_arn',
    'arn_type',
    'arn_name',
    'before_colon',
    'after_colon',
    'before_dot',
    'first_label',
    'lower',
    'strip_leading_slash',
    'ensure_trailing_slash',
    'strip_wildcard_suffix',
    'secret_name',
    's3uri_dir',
    'prefix_dir',
    's3_target_object',
    'filters_first_value',
]


class BaseParamsTest(unittest.TestCase):
    def check(self, name, values, expected):
        self.assertEqual(
            params.parse_param(name, values), expected, (name, values)
        )


class TestEmptyAndAbsent(BaseParamsTest):
    def test_every_new_function_is_registered(self):
        for name in NEW_FUNCTIONS:
            with self.subTest(name=name):
                self.assertIs(params.PARSERS[name], getattr(params, name))

    def test_only_present_accepts_an_empty_list(self):
        for name in sorted(params.PARSERS):
            with self.subTest(name=name):
                expected = '1' if name == 'present' else None
                self.assertEqual(params.parse_param(name, []), expected)

    def test_absent_argument_is_none_for_every_function(self):
        for name in sorted(params.PARSERS):
            with self.subTest(name=name):
                self.assertIsNone(params.parse_param(name, None))


class TestPresent(BaseParamsTest):
    def test_present(self):
        self.check('present', [], '1')
        self.check('present', ['x'], '1')
        self.check('present', ['a', 'b'], '1')
        self.check('present', None, None)


class TestArnFunctions(BaseParamsTest):
    def test_is_arn(self):
        self.check('is_arn', [ROLE], ROLE)
        self.check('is_arn', ['arn:aws:s3:::bucket'], 'arn:aws:s3:::bucket')
        self.check('is_arn', ['my-role'], None)
        self.check('is_arn', ['arn:aws'], None)
        self.check('is_arn', ['arn::iam::1:role/x'], None)

    def test_arn_type(self):
        self.check('arn_type', [KMS_KEY], 'key')
        self.check('arn_type', [KMS_ALIAS], 'alias')
        self.check('arn_type', [ROLE], 'role')
        self.check(
            'arn_type',
            ['arn:aws:lambda:us-west-2:111122223333:function:f'],
            'function',
        )
        self.check('arn_type', [TOPIC], None)
        self.check('arn_type', ['key/1234'], None)

    def test_arn_name(self):
        self.check('arn_name', [ROLE], 'MyRole')
        self.check('arn_name', [KMS_ALIAS], 'my-alias')
        self.check('arn_name', [TOPIC], 'my-topic')
        self.check('arn_name', ['arn:aws:iam::1:role/'], None)
        self.check('arn_name', ['MyRole'], None)

    def test_secret_name(self):
        self.check('secret_name', [SECRET], 'prod/db')
        self.check(
            'secret_name',
            ['arn:aws:secretsmanager:us-west-2:1:secret:MySecret-a1B2c3'],
            'MySecret',
        )
        self.check('secret_name', ['MySecret'], 'MySecret')
        self.check('secret_name', ['prod/db-AbCdEf'], 'prod/db-AbCdEf')


class TestStringFunctions(BaseParamsTest):
    def test_before_colon(self):
        self.check('before_colon', ['repo:tag'], 'repo')
        self.check('before_colon', ['a:b:c'], 'a')
        self.check('before_colon', ['plain'], 'plain')
        self.check('before_colon', [':x'], None)

    def test_after_colon(self):
        self.check('after_colon', ['repo:tag'], 'tag')
        self.check('after_colon', ['a:b:c'], 'b:c')
        self.check('after_colon', ['plain'], None)
        self.check('after_colon', ['x:'], None)

    def test_before_dot(self):
        self.check('before_dot', ['index.handler'], 'index')
        self.check('before_dot', ['a.b.c'], 'a')
        self.check('before_dot', ['plain'], 'plain')

    def test_first_label(self):
        self.check(
            'first_label',
            ['my-domain.us-west-2.es.amazonaws.com'],
            'my-domain',
        )
        self.check('first_label', ['https://abc.example.com/path'], 'abc')
        self.check('first_label', ['localhost'], 'localhost')

    def test_lower(self):
        self.check('lower', ['MyCluster'], 'mycluster')
        self.check('lower', ['already'], 'already')
        self.check('lower', [''], None)

    def test_strip_leading_slash(self):
        self.check('strip_leading_slash', ['/aws/lambda/f'], 'aws/lambda/f')
        self.check('strip_leading_slash', ['//x'], '/x')
        self.check('strip_leading_slash', ['x'], 'x')
        self.check('strip_leading_slash', ['/'], None)

    def test_ensure_trailing_slash(self):
        self.check('ensure_trailing_slash', ['/app'], '/app/')
        self.check('ensure_trailing_slash', ['/app/'], '/app/')
        self.check('ensure_trailing_slash', [''], None)

    def test_strip_wildcard_suffix(self):
        self.check(
            'strip_wildcard_suffix',
            [LOG_GROUP],
            'arn:aws:logs:us-west-2:111122223333:log-group:/aws/lambda/f',
        )
        self.check('strip_wildcard_suffix', ['name'], 'name')
        self.check('strip_wildcard_suffix', ['a*'], 'a*')

    def test_uses_the_first_value(self):
        self.check('lower', ['A', 'B'], 'a')
        self.check('before_dot', ['a.b', 'c.d'], 'a')


class TestS3Functions(BaseParamsTest):
    def test_s3uri_dir(self):
        self.check('s3uri_dir', ['s3://b/logs'], 'logs/')
        self.check('s3uri_dir', ['s3://b/logs/'], 'logs/')
        self.check('s3uri_dir', ['s3://b/a/b'], 'a/b/')
        self.check('s3uri_dir', ['local', 's3://b/x'], 'x/')
        self.check('s3uri_dir', ['s3://b'], None)
        self.check('s3uri_dir', ['s3://b/'], None)

    def test_prefix_dir(self):
        self.check('prefix_dir', ['photos/2026'], 'photos/')
        self.check('prefix_dir', ['photos/2026/'], 'photos/2026/')
        self.check('prefix_dir', ['a/b/c'], 'a/b/')
        self.check('prefix_dir', ['photos'], None)

    def test_s3_target_object(self):
        self.check('s3_target_object', ['f.txt', 's3://b/k/f.txt'], 'k/f.txt')
        self.check('s3_target_object', ['s3://b/k/f.txt', 'f.txt'], 'k/f.txt')
        self.check('s3_target_object', ['f.txt', 's3://b/k/'], None)
        self.check('s3_target_object', ['f.txt', 's3://b'], None)


class TestFiltersFirstValue(BaseParamsTest):
    def test_filters_first_value(self):
        self.check('filters_first_value', ['Name=tag:Name,Values=a,b'], 'a')
        self.check(
            'filters_first_value', ['Name=instance-id,Values=i-1'], 'i-1'
        )
        self.check(
            'filters_first_value',
            ['Name=x,Values=v1', 'Name=y,Values=v2'],
            'v1',
        )
        self.check('filters_first_value', ['Name=x'], None)
        self.check('filters_first_value', ['Name=x,Values='], None)
