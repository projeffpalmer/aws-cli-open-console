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
from botocore.exceptions import ClientError, NoCredentialsError

from awscli.customizations.openconsole.account import (
    AccountResolver,
)
from awscli.testutils import mock, unittest

ACCOUNT = '123456789012'
ROOT_ARN = f'arn:aws:iam::{ACCOUNT}:root'


def make_session(identity=None, error=None):
    client = mock.Mock()
    if error is not None:
        client.get_caller_identity.side_effect = error
    else:
        client.get_caller_identity.return_value = identity or {}
    session = mock.Mock()
    session.create_client.return_value = client
    return session, client


class TestAccountResolver(unittest.TestCase):
    def test_caller_arn_calls_sts_once_and_caches(self):
        session, client = make_session({'Account': ACCOUNT, 'Arn': ROOT_ARN})
        resolver = AccountResolver(session, 'eu-west-1')
        self.assertEqual(resolver.caller_arn(), ROOT_ARN)
        self.assertEqual(resolver.caller_arn(), ROOT_ARN)
        session.create_client.assert_called_once_with(
            'sts', region_name='eu-west-1'
        )
        client.get_caller_identity.assert_called_once_with()

    def test_sts_is_not_called_until_the_arn_is_asked_for(self):
        session, client = make_session({'Arn': ROOT_ARN})
        AccountResolver(session, 'us-west-2')
        session.create_client.assert_not_called()

    def test_failure_is_cached_as_none(self):
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'no'}},
            'GetCallerIdentity',
        )
        session, client = make_session(error=error)
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.caller_arn())
        self.assertIsNone(resolver.caller_arn())
        client.get_caller_identity.assert_called_once_with()

    def test_botocore_error_is_cached_as_none(self):
        session, client = make_session(error=NoCredentialsError())
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.caller_arn())
        self.assertIsNone(resolver.caller_arn())
        client.get_caller_identity.assert_called_once_with()

    def test_create_client_failure_is_cached_as_none(self):
        session = mock.Mock()
        session.create_client.side_effect = NoCredentialsError()
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.caller_arn())
        self.assertIsNone(resolver.caller_arn())
        session.create_client.assert_called_once()

    def test_unusable_response_is_none(self):
        for identity in ({'Arn': 12345}, {'Account': ACCOUNT}, 'not-a-dict'):
            with self.subTest(identity=identity):
                session, client = make_session(identity)
                resolver = AccountResolver(session, 'us-west-2')
                self.assertIsNone(resolver.caller_arn())
                client.get_caller_identity.assert_called_once_with()
