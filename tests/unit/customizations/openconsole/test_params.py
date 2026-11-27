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
from awscli.customizations.openconsole import params
from awscli.testutils import unittest

LOG_GROUP = 'arn:aws:logs:us-west-2:111122223333:log-group:/aws/lambda/f'
ROLE = 'arn:aws:iam::111122223333:role/service-role/MyRole'


class BaseParamsTest(unittest.TestCase):
    def check(self, name, values, expected):
        self.assertEqual(
            getattr(params, name)(values), expected, (name, values)
        )


class TestFirst(BaseParamsTest):
    def test_first(self):
        self.check('first', ['a', 'b'], 'a')
        self.check('first', [], None)
        self.check('first', None, None)


class TestS3Uri(BaseParamsTest):
    def test_s3uri_bucket(self):
        self.check('s3uri_bucket', ['s3://b/k/f.txt'], 'b')
        self.check('s3uri_bucket', ['s3://b'], 'b')
        self.check('s3uri_bucket', ['b/k'], 'b')
        self.check('s3uri_bucket', ['local', 's3://b/x'], 'b')
        self.check('s3uri_bucket', ['s3://'], None)
        self.check('s3uri_bucket', [], None)
        self.check('s3uri_bucket', [7], None)

    def test_s3uri_prefix(self):
        self.check('s3uri_prefix', ['s3://b/k/f.txt'], 'k/')
        self.check('s3uri_prefix', ['s3://b/k/'], 'k/')
        self.check('s3uri_prefix', ['s3://b/f.txt'], None)
        self.check('s3uri_prefix', ['s3://b'], None)

    def test_s3uri_object(self):
        self.check('s3uri_object', ['s3://b/k/f.txt'], 'k/f.txt')
        self.check('s3uri_object', ['s3://b/k/'], None)
        self.check('s3uri_object', ['s3://b'], None)

    def test_s3uri_dir(self):
        self.check('s3uri_dir', ['s3://b/logs'], 'logs/')
        self.check('s3uri_dir', ['s3://b/logs/'], 'logs/')
        self.check('s3uri_dir', ['s3://b/a/b'], 'a/b/')
        self.check('s3uri_dir', ['local', 's3://b/x'], 'x/')
        self.check('s3uri_dir', ['s3://b'], None)
        self.check('s3uri_dir', ['s3://b/'], None)


class TestS3Target(BaseParamsTest):
    def test_s3_target_bucket(self):
        self.check('s3_target_bucket', ['f.txt', 's3://b/k'], 'b')
        self.check('s3_target_bucket', ['s3://src/k', 's3://dst/k'], 'dst')
        self.check('s3_target_bucket', ['s3://b/k', 'f.txt'], 'b')

    def test_s3_target_prefix(self):
        self.check('s3_target_prefix', ['f.txt', 's3://b/k/f.txt'], 'k/')
        self.check('s3_target_prefix', ['f.txt', 's3://b/f.txt'], None)

    def test_s3_target_object(self):
        self.check('s3_target_object', ['f.txt', 's3://b/k/f.txt'], 'k/f.txt')
        self.check('s3_target_object', ['s3://b/k/f.txt', 'f.txt'], 'k/f.txt')
        self.check('s3_target_object', ['f.txt', 's3://b/k/'], None)
        self.check('s3_target_object', ['f.txt', 's3://b'], None)

    def test_s3_target_dir(self):
        self.check('s3_target_dir', ['dir', 's3://b/backup'], 'backup/')
        self.check('s3_target_dir', ['dir', 's3://b/a/b/'], 'a/b/')
        self.check('s3_target_dir', ['s3://b/a/b', 'dir'], 'a/b/')
        self.check('s3_target_dir', ['s3://src/x', 's3://dst/y'], 'y/')
        self.check('s3_target_dir', ['dir', 's3://b'], None)


class TestArnResource(BaseParamsTest):
    def test_arn_resource(self):
        self.check('arn_resource', [LOG_GROUP], '/aws/lambda/f')
        self.check('arn_resource', [ROLE], 'service-role/MyRole')
        self.check('arn_resource', ['arn:aws:s3:::bucket'], 'bucket')
        self.check('arn_resource', ['not-an-arn'], None)
        self.check('arn_resource', ['arn:aws:iam::1:role/'], None)
        self.check('arn_resource', [None], None)
