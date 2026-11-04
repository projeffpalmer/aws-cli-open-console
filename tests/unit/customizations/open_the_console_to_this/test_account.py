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
from botocore.exceptions import ClientError, NoCredentialsError

from awscli.customizations.open_the_console_to_this.account import (
    AccountResolver,
)
from awscli.testutils import mock, unittest

ACCOUNT = '123456789012'
FEDERATED_ARN = f'arn:aws:sts::{ACCOUNT}:federated-user/open-the-console'


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
    def test_get_calls_sts_once_and_caches(self):
        session, client = make_session({'Account': ACCOUNT})
        resolver = AccountResolver(session, 'eu-west-1')
        self.assertEqual(resolver.get(), ACCOUNT)
        self.assertEqual(resolver.get(), ACCOUNT)
        session.create_client.assert_called_once_with(
            'sts', region_name='eu-west-1'
        )
        client.get_caller_identity.assert_called_once_with()

    def test_failure_is_cached_as_none(self):
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'no'}},
            'GetCallerIdentity',
        )
        session, client = make_session(error=error)
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.get())
        self.assertIsNone(resolver.get())
        client.get_caller_identity.assert_called_once_with()

    def test_botocore_error_is_cached_as_none(self):
        session, client = make_session(error=NoCredentialsError())
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.get())
        self.assertIsNone(resolver.get())
        client.get_caller_identity.assert_called_once_with()

    def test_create_client_failure_is_cached_as_none(self):
        session = mock.Mock()
        session.create_client.side_effect = NoCredentialsError()
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.get())
        self.assertIsNone(resolver.get())
        session.create_client.assert_called_once()

    def test_unusable_account_value_is_none(self):
        session, client = make_session({'Account': 'not-an-id'})
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.get())
        self.assertIsNone(resolver.get())
        client.get_caller_identity.assert_called_once_with()

    def test_set_from_arn_avoids_the_sts_call(self):
        session, client = make_session({'Account': '999999999999'})
        resolver = AccountResolver(session, 'us-west-2')
        resolver.set_from_arn(FEDERATED_ARN)
        self.assertEqual(resolver.get(), ACCOUNT)
        session.create_client.assert_not_called()

    def test_set_from_arn_ignores_invalid_arns(self):
        for arn in (
            None,
            '',
            'not-an-arn',
            'arn:aws:s3:::bucket',
            'arn:aws:sts::12345:federated-user/x',
            'arn:aws:sts::1234567890123:federated-user/x',
            'arn:aws:sts::12345678901a:federated-user/x',
        ):
            with self.subTest(arn=arn):
                session, client = make_session({'Account': ACCOUNT})
                resolver = AccountResolver(session, 'us-west-2')
                resolver.set_from_arn(arn)
                self.assertEqual(resolver.get(), ACCOUNT)
                client.get_caller_identity.assert_called_once_with()

    def test_set_from_arn_after_failed_lookup(self):
        session, client = make_session(error=NoCredentialsError())
        resolver = AccountResolver(session, 'us-west-2')
        self.assertIsNone(resolver.get())
        resolver.set_from_arn(FEDERATED_ARN)
        self.assertEqual(resolver.get(), ACCOUNT)
        client.get_caller_identity.assert_called_once_with()
