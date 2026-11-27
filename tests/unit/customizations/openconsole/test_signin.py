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
import hashlib
import json
import logging
import os
from urllib.parse import parse_qs, quote_plus, urlsplit

from botocore.exceptions import (
    ClientError,
    CredentialRetrievalError,
    EndpointConnectionError,
    NoCredentialsError,
    UnauthorizedSSOTokenError,
)

from awscli.customizations.openconsole import signin
from awscli.customizations.openconsole.account import (
    AccountResolver,
)
from awscli.testutils import mock, unittest

ACCOUNT = '123456789012'
FEDERATED_ARN = f'arn:aws:sts::{ACCOUNT}:federated-user/{signin.ISSUER}'
ROLE_ARN = f'arn:aws:sts::{ACCOUNT}:assumed-role/Admin/session'
ROOT_ARN = f'arn:aws:iam::{ACCOUNT}:root'
USER_ARN = f'arn:aws:iam::{ACCOUNT}:user/alice'
DESTINATION = (
    'https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2'
    '#InstanceDetails:instanceId=i-0123456789abcdef0&x=1'
)
LONG_KEYS = ('AKIDLONGTERMKEY0001', 'long/term+secret=key', None)
TEMP_KEYS = ('ASIATEMPKEY00000001', 'temp/secret+key=', 'temp+session/token=')
FED_KEYS = ('ASIAFEDERATED000001', 'fed/secret+key=', 'fed+session/token=')
SIGNIN_TOKEN = 'signin+token/value='
NO_SIGNIN = 'Opening the console without signing in.'
HOSTS = {
    'aws': 'signin.aws.amazon.com',
    'aws-us-gov': 'signin.amazonaws-us-gov.com',
    'aws-cn': 'signin.amazonaws.cn',
}


def secrets_of(*key_sets):
    values = [SIGNIN_TOKEN]
    for key_set in key_sets:
        values.extend(value for value in key_set[1:] if value)
    return values + [quote_plus(value) for value in values]


def make_credentials(keys, method='env'):
    access_key, secret_key, token = keys
    creds = mock.Mock()
    creds.method = method
    frozen = mock.Mock(access_key=access_key, secret_key=secret_key)
    frozen.token = token
    creds.get_frozen_credentials.return_value = frozen
    return creds


def federation_response():
    access_key, secret_key, token = FED_KEYS
    return {
        'Credentials': {
            'AccessKeyId': access_key,
            'SecretAccessKey': secret_key,
            'SessionToken': token,
            'Expiration': '2026-11-04T12:00:00Z',
        },
        'FederatedUser': {
            'FederatedUserId': f'{ACCOUNT}:{signin.ISSUER}',
            'Arn': FEDERATED_ARN,
        },
    }


def make_session(
    keys=TEMP_KEYS,
    sts_response=None,
    sts_error=None,
    ca_bundle=None,
    method='env',
    caller_arn=ROLE_ARN,
):
    session = mock.Mock()
    session.get_config_variable.return_value = ca_bundle
    session.get_credentials.return_value = (
        None if keys is None else make_credentials(keys, method)
    )
    sts = mock.Mock()
    sts.get_caller_identity.return_value = {
        'Account': ACCOUNT,
        'Arn': caller_arn,
    }
    if sts_error is not None:
        sts.get_federation_token.side_effect = sts_error
    else:
        sts.get_federation_token.return_value = (
            sts_response or federation_response()
        )
    session.create_client.return_value = sts
    return session, sts


def http_ok(token=SIGNIN_TOKEN):
    return mock.Mock(return_value=(200, json.dumps({'SigninToken': token})))


def query_of(url):
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []
        self.setFormatter(logging.Formatter('%(name)s %(message)s'))

    def emit(self, record):
        self.records.append(self.format(record))


class SigninTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(signin, '_http_get', http_ok())
        self.http_get = patcher.start()
        self.addCleanup(patcher.stop)

    def capture_logs(self):
        handler = _Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        for name in ('', 'awscli', 'botocore', 'urllib3'):
            logger = logging.getLogger(name)
            self.addCleanup(logger.setLevel, logger.level)
            logger.setLevel(logging.DEBUG)
        return handler

    def assert_no_secrets(self, records, secrets):
        self.assertTrue(records)
        for record in records:
            for secret in secrets:
                self.assertNotIn(secret, record)

    def session_param(self):
        url = self.http_get.call_args[0][1]
        return json.loads(query_of(url)['Session'][0])


class TestConstants(unittest.TestCase):
    def test_issuer_and_policy(self):
        self.assertEqual(signin.ISSUER, 'aws-cli')
        self.assertEqual(
            signin.FEDERATION_POLICY,
            '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
            '"Action":"*","Resource":"*"}]}',
        )
        json.loads(signin.FEDERATION_POLICY)


class TestResolveCredentials(unittest.TestCase):
    def test_no_credentials(self):
        session = mock.Mock()
        session.get_credentials.return_value = None
        self.assertEqual(
            signin.resolve_credentials(session),
            (
                None,
                'Unable to locate credentials. Opening the console '
                'without signing in.',
            ),
        )

    def test_no_credentials_error_from_provider(self):
        session = mock.Mock()
        session.get_credentials.side_effect = NoCredentialsError()
        self.assertEqual(
            signin.resolve_credentials(session),
            (
                None,
                'Unable to locate credentials. Opening the console '
                'without signing in.',
            ),
        )

    def test_refresh_error_from_frozen_credentials(self):
        session = mock.Mock()
        creds = session.get_credentials.return_value
        creds.get_frozen_credentials.side_effect = UnauthorizedSSOTokenError()
        frozen, warning = signin.resolve_credentials(session)
        self.assertIsNone(frozen)
        message = str(UnauthorizedSSOTokenError()).rstrip('.')
        self.assertEqual(warning, f'{message}. {NO_SIGNIN}')
        self.assertNotIn('..', warning)

    def test_client_error_from_provider(self):
        session = mock.Mock()
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'denied'}},
            'AssumeRole',
        )
        session.get_credentials.side_effect = error
        self.assertEqual(
            signin.resolve_credentials(session),
            (None, f'{error}. {NO_SIGNIN}'),
        )

    def test_multi_line_provider_error_gives_one_line(self):
        session = mock.Mock()
        session.get_credentials.side_effect = CredentialRetrievalError(
            provider='custom-process', error_msg='a\nb'
        )
        frozen, warning = signin.resolve_credentials(session)
        self.assertIsNone(frozen)
        self.assertNotIn('\n', warning)
        self.assertTrue(
            warning.endswith('. Opening the console without signing in.'),
            warning,
        )
        self.assertIn('a b', warning)

    def test_frozen_credentials_and_method(self):
        session = mock.Mock()
        session.get_credentials.return_value = make_credentials(
            TEMP_KEYS, method='sso'
        )
        frozen, warning = signin.resolve_credentials(session)
        self.assertIsNone(warning)
        self.assertEqual(
            (frozen.access_key, frozen.secret_key, frozen.token), TEMP_KEYS
        )
        self.assertEqual(frozen.method, 'sso')
        for secret in TEMP_KEYS:
            self.assertNotIn(secret, repr(frozen))
            self.assertNotIn(secret, str(frozen))


class TestSigninUrl(unittest.TestCase):
    def setUp(self):
        self.url = signin.SigninUrl(HOSTS['aws'], DESTINATION, SIGNIN_TOKEN)
        self.token_hash = signin.hashed(SIGNIN_TOKEN)

    def assert_token_hashed(self, text):
        for secret in secrets_of():
            self.assertNotIn(secret, text)
        self.assertIn(f'SigninToken={self.token_hash}', text)

    def test_hash_is_the_start_of_the_sha256(self):
        digest = hashlib.sha256(SIGNIN_TOKEN.encode('utf-8')).hexdigest()
        self.assertEqual(self.token_hash, f'sha256:{digest[:16]}')
        self.assertNotEqual(signin.hashed('another token'), self.token_hash)

    def test_unhashed_is_the_url_that_signs_in(self):
        url = self.url.unhashed()
        self.assertTrue(
            url.startswith('https://signin.aws.amazon.com/federation?')
        )
        self.assertEqual(
            query_of(url),
            {
                'Action': ['login'],
                'Issuer': [signin.ISSUER],
                'Destination': [DESTINATION],
                'SigninToken': [SIGNIN_TOKEN],
            },
        )

    def test_printed_and_formatted_forms_have_the_token_hashed(self):
        forms = {
            'str': str(self.url),
            'repr': repr(self.url),
            'f-string': f'{self.url}',
        }
        for name, text in forms.items():
            with self.subTest(form=name):
                self.assert_token_hashed(text)

    def test_str_is_the_login_url_with_only_the_token_replaced(self):
        self.assertEqual(
            str(self.url),
            self.url.unhashed().replace(
                quote_plus(SIGNIN_TOKEN), self.token_hash
            ),
        )

    def test_logging_the_url_logs_the_hash(self):
        with self.assertLogs('signin-url-test', 'DEBUG') as logs:
            logging.getLogger('signin-url-test').debug('open %s', self.url)
        self.assert_token_hashed('\n'.join(logs.output))

    def test_hashed_in_hashes_every_quoted_form_of_the_token(self):
        text = (
            f'cannot run {self.url.unhashed()}; token {SIGNIN_TOKEN}; '
            f'encoded {quote_plus(SIGNIN_TOKEN)}'
        )
        self.assertEqual(
            self.url.hashed_in(text),
            f'cannot run {self.url}; token {self.token_hash}; '
            f'encoded {self.token_hash}',
        )

    def test_hashed_in_leaves_other_text_alone(self):
        self.assertEqual(self.url.hashed_in('no browser'), 'no browser')

    def test_only_the_browser_launcher_unhashes(self):
        package = os.path.dirname(signin.__file__)
        calls = {}
        for name in sorted(os.listdir(package)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(package, name), encoding='utf-8') as f:
                count = f.read().count('.unhashed(')
            if count:
                calls[name] = count
        self.assertEqual(calls, {'browser.py': 1})


class TestFederationLoginUrl(SigninTestCase):
    def login_url(self, session, keys=TEMP_KEYS, partition='aws', **kwargs):
        """Return the URL that the browser is given."""
        frozen, _ = signin.resolve_credentials(session)
        return signin.federation_login_url(
            session,
            frozen,
            kwargs.get('destination', DESTINATION),
            partition,
            kwargs.get('region', 'us-west-2'),
            kwargs.get(
                'account_resolver', AccountResolver(session, 'us-west-2')
            ),
        ).unhashed()

    def test_role_session_providers_skip_sts(self):
        for method in sorted(signin.ROLE_SESSION_PROVIDERS):
            with self.subTest(method=method):
                session, sts = make_session(TEMP_KEYS, method=method)
                self.login_url(session)
                session.create_client.assert_not_called()

    def test_other_temporary_credentials_check_the_identity_only(self):
        for arn in (ROLE_ARN, FEDERATED_ARN):
            with self.subTest(arn=arn):
                session, sts = make_session(TEMP_KEYS, caller_arn=arn)
                resolver = AccountResolver(session, 'us-west-2')
                self.login_url(session, account_resolver=resolver)
                sts.get_caller_identity.assert_called_once_with()
                sts.get_federation_token.assert_not_called()

    def test_non_role_temporary_credentials_are_refused(self):
        cases = [
            (ROOT_ARN, 'login', 'root user'),
            (USER_ARN, 'login', 'IAM user'),
            (USER_ARN, 'env', 'IAM user'),
            (ROOT_ARN, 'shared-credentials-file', 'root user'),
        ]
        for arn, method, kind in cases:
            with self.subTest(arn=arn, method=method):
                self.http_get.reset_mock()
                session, sts = make_session(
                    TEMP_KEYS, method=method, caller_arn=arn
                )
                self.assert_signin_error(
                    session,
                    f'{kind} session credentials cannot sign in to the '
                    'console through federation; only role and federated '
                    'user sessions can',
                    secrets=secrets_of(TEMP_KEYS),
                )
                self.http_get.assert_not_called()
                sts.get_federation_token.assert_not_called()

    def test_unknown_identity_still_attempts_signin(self):
        session, sts = make_session(TEMP_KEYS, method='login')
        sts.get_caller_identity.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'no'}},
            'GetCallerIdentity',
        )
        url = self.login_url(session)
        self.assertEqual(query_of(url)['SigninToken'], [SIGNIN_TOKEN])

    def test_temporary_credentials_skip_get_federation_token(self):
        session, sts = make_session(TEMP_KEYS)
        self.login_url(session)
        sts.get_federation_token.assert_not_called()
        self.assertEqual(
            self.session_param(),
            {
                'sessionId': TEMP_KEYS[0],
                'sessionKey': TEMP_KEYS[1],
                'sessionToken': TEMP_KEYS[2],
            },
        )

    def test_get_signin_token_request(self):
        session, _ = make_session(TEMP_KEYS)
        self.login_url(session)
        self.http_get.assert_called_once()
        called_session, url = self.http_get.call_args[0]
        self.assertIs(called_session, session)
        parts = urlsplit(url)
        self.assertEqual(
            (parts.scheme, parts.netloc, parts.path, parts.fragment),
            ('https', 'signin.aws.amazon.com', '/federation', ''),
        )
        self.assertEqual(sorted(query_of(url)), ['Action', 'Session'])
        self.assertEqual(query_of(url)['Action'], ['getSigninToken'])
        self.assertNotIn('SessionDuration', url)
        session_json = json.dumps(
            {
                'sessionId': TEMP_KEYS[0],
                'sessionKey': TEMP_KEYS[1],
                'sessionToken': TEMP_KEYS[2],
            }
        )
        self.assertEqual(
            parts.query,
            f'Action=getSigninToken&Session={quote_plus(session_json)}',
        )

    def test_login_url(self):
        session, _ = make_session(TEMP_KEYS)
        url = self.login_url(session)
        parts = urlsplit(url)
        self.assertEqual(
            (parts.scheme, parts.netloc, parts.path, parts.fragment),
            ('https', 'signin.aws.amazon.com', '/federation', ''),
        )
        self.assertEqual(
            query_of(url),
            {
                'Action': ['login'],
                'Issuer': [signin.ISSUER],
                'Destination': [DESTINATION],
                'SigninToken': [SIGNIN_TOKEN],
            },
        )
        self.assertEqual(
            parts.query,
            'Action=login&Issuer=aws-cli'
            f'&Destination={quote_plus(DESTINATION)}'
            f'&SigninToken={quote_plus(SIGNIN_TOKEN)}',
        )
        self.assertNotIn('SessionDuration', url)

    def test_partition_hosts(self):
        for partition, host in HOSTS.items():
            with self.subTest(partition=partition):
                self.http_get.reset_mock()
                session, _ = make_session(TEMP_KEYS)
                url = self.login_url(session, partition=partition)
                self.assertEqual(urlsplit(url).netloc, host)
                token_url = self.http_get.call_args[0][1]
                self.assertEqual(urlsplit(token_url).netloc, host)

    def test_long_term_keys_call_get_federation_token(self):
        session, sts = make_session(LONG_KEYS)
        resolver = AccountResolver(session, 'eu-central-1')
        url = self.login_url(
            session, region='eu-central-1', account_resolver=resolver
        )
        session.create_client.assert_called_once_with(
            'sts', region_name='eu-central-1'
        )
        sts.get_federation_token.assert_called_once_with(
            Name='aws-cli',
            Policy=signin.FEDERATION_POLICY,
            DurationSeconds=3600,
        )
        self.assertEqual(
            self.session_param(),
            {
                'sessionId': FED_KEYS[0],
                'sessionKey': FED_KEYS[1],
                'sessionToken': FED_KEYS[2],
            },
        )
        self.assertEqual(query_of(url)['SigninToken'], [SIGNIN_TOKEN])
        self.assertNotIn('SessionDuration', self.http_get.call_args[0][1])
        sts.get_caller_identity.assert_not_called()
        self.assertEqual(session.create_client.call_count, 1)

    def run_with_fake_recorder(self, enabled, sts_error=None):
        calls = []

        class FakeRecorder:
            _enabled = enabled

            def disable(self):
                calls.append('disable')

            def enable(self):
                calls.append('enable')

        def get_federation_token(**kwargs):
            calls.append('GetFederationToken')
            if sts_error is not None:
                raise sts_error
            return federation_response()

        session, sts = make_session(LONG_KEYS)
        sts.get_federation_token.side_effect = get_federation_token
        with mock.patch.object(
            signin, 'get_global_history_recorder', FakeRecorder
        ):
            try:
                self.login_url(session)
            except signin.SigninError:
                pass
        return calls

    def test_history_is_paused_around_get_federation_token(self):
        self.assertEqual(
            self.run_with_fake_recorder(True),
            ['disable', 'GetFederationToken', 'enable'],
        )

    def test_history_is_re_enabled_after_an_sts_error(self):
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'no'}},
            'GetFederationToken',
        )
        self.assertEqual(
            self.run_with_fake_recorder(True, sts_error=error),
            ['disable', 'GetFederationToken', 'enable'],
        )

    def test_disabled_history_is_left_alone(self):
        self.assertEqual(
            self.run_with_fake_recorder(False), ['GetFederationToken']
        )

    def assert_signin_error(self, session, reason, secrets=()):
        with self.assertRaises(signin.SigninError) as cm:
            self.login_url(session)
        self.assertEqual(cm.exception.reason, reason)
        for secret in secrets:
            self.assertNotIn(secret, cm.exception.reason)

    def test_blank_ca_bundle_fails_before_any_request(self):
        for ca_bundle in ('', '   '):
            for keys in (TEMP_KEYS, LONG_KEYS):
                with self.subTest(ca_bundle=ca_bundle, keys=keys[0]):
                    self.http_get.reset_mock()
                    session, sts = make_session(keys, ca_bundle=ca_bundle)
                    self.assert_signin_error(
                        session, 'invalid ca_bundle configuration'
                    )
                    self.assertFalse(self.http_get.called)
                    self.assertFalse(session.create_client.called)
                    self.assertFalse(sts.get_federation_token.called)

    def test_sts_client_error(self):
        error = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'not allowed'}},
            'GetFederationToken',
        )
        session, _ = make_session(LONG_KEYS, sts_error=error)
        self.assert_signin_error(
            session, 'GetFederationToken failed: AccessDenied: not allowed'
        )
        self.http_get.assert_not_called()

    def test_sts_botocore_error(self):
        error = EndpointConnectionError(endpoint_url='https://sts.example')
        session, _ = make_session(LONG_KEYS, sts_error=error)
        self.assert_signin_error(
            session, f'GetFederationToken failed: {error}'
        )
        self.http_get.assert_not_called()

    def test_sts_unexpected_response(self):
        session, _ = make_session(LONG_KEYS, sts_response={'Other': 1})
        self.assert_signin_error(
            session, 'unexpected GetFederationToken response'
        )

    def test_non_200(self):
        self.http_get.return_value = (400, 'bad request')
        session, _ = make_session(TEMP_KEYS)
        self.assert_signin_error(
            session, 'signin.aws.amazon.com returned HTTP 400'
        )

    def test_unparsable_body(self):
        for body in ('<html>', '[]', '"text"', None):
            with self.subTest(body=body):
                self.http_get.return_value = (200, body)
                session, _ = make_session(TEMP_KEYS)
                self.assert_signin_error(
                    session, 'unexpected response from signin.aws.amazon.com'
                )

    def test_missing_token(self):
        for body in ('{}', '{"SigninToken": ""}', '{"SigninToken": 7}'):
            with self.subTest(body=body):
                self.http_get.return_value = (200, body)
                session, _ = make_session(TEMP_KEYS)
                self.assert_signin_error(
                    session,
                    'no sign-in token in the response from '
                    'signin.aws.amazon.com',
                )

    def test_network_error_reason_has_no_url(self):
        def fail(session, url):
            raise EndpointConnectionError(endpoint_url=url)

        self.http_get.side_effect = fail
        session, _ = make_session(TEMP_KEYS)
        self.assert_signin_error(
            session,
            'could not reach signin.aws.amazon.com: EndpointConnectionError',
            secrets=secrets_of(TEMP_KEYS),
        )


class TestWrap(SigninTestCase):
    def wrap(self, session, partition='aws'):
        return signin.wrap(
            session,
            DESTINATION,
            partition,
            'us-west-2',
            AccountResolver(session, 'us-west-2'),
        )

    def test_aws_login_root_session_opens_plain_url_with_warning(self):
        session, _ = make_session(
            TEMP_KEYS, method='login', caller_arn=ROOT_ARN
        )
        self.assertEqual(
            self.wrap(session),
            (
                DESTINATION,
                'Console sign-in failed (root user session credentials '
                'cannot sign in to the console through federation; only '
                'role and federated user sessions can). '
                f'{NO_SIGNIN}',
            ),
        )
        self.http_get.assert_not_called()

    def test_no_credentials(self):
        session, _ = make_session(None)
        self.assertEqual(
            self.wrap(session),
            (
                DESTINATION,
                'Unable to locate credentials. Opening the console '
                'without signing in.',
            ),
        )
        session.create_client.assert_not_called()
        self.http_get.assert_not_called()

    def test_credential_provider_error(self):
        session, _ = make_session(None)
        session.get_credentials.side_effect = UnauthorizedSSOTokenError()
        url, warning = self.wrap(session)
        self.assertEqual(url, DESTINATION)
        self.assertTrue(warning.endswith(f'. {NO_SIGNIN}'))
        self.http_get.assert_not_called()

    def test_blank_ca_bundle_opens_plain_url_with_warning(self):
        session, _ = make_session(TEMP_KEYS, ca_bundle='')
        self.assertEqual(
            self.wrap(session),
            (
                DESTINATION,
                'Console sign-in failed (invalid ca_bundle configuration). '
                f'{NO_SIGNIN}',
            ),
        )
        self.http_get.assert_not_called()

    def test_signin_failure(self):
        self.http_get.return_value = (500, 'oops')
        session, _ = make_session(TEMP_KEYS)
        self.assertEqual(
            self.wrap(session),
            (
                DESTINATION,
                'Console sign-in failed (signin.aws.amazon.com returned '
                'HTTP 500). Opening the console without signing in.',
            ),
        )

    def test_success(self):
        session, _ = make_session(TEMP_KEYS)
        url, warning = self.wrap(session, partition='aws-cn')
        self.assertIsNone(warning)
        self.assertIsInstance(url, signin.SigninUrl)
        login_url = url.unhashed()
        self.assertTrue(
            login_url.startswith('https://signin.amazonaws.cn/federation?')
        )
        self.assertEqual(query_of(login_url)['Destination'], [DESTINATION])
        self.assertEqual(query_of(login_url)['SigninToken'], [SIGNIN_TOKEN])
        for secret in secrets_of():
            self.assertNotIn(secret, str(url))


class TestNoSecretsInLogs(SigninTestCase):
    def simulate_library_logs(self):
        """Log the way urllib3 and botocore do under ``--debug``."""

        def get(session, url):
            logging.getLogger('urllib3.connectionpool').debug(
                'https://%s:443 "GET %s HTTP/1.1" 200 42', 'host', url
            )
            logging.getLogger('botocore.httpsession').debug(
                'Exception received',
                exc_info=EndpointConnectionError(endpoint_url=url),
            )
            return 200, json.dumps({'SigninToken': SIGNIN_TOKEN})

        def get_federation_token(**kwargs):
            body = json.dumps(federation_response())
            logging.getLogger('botocore.parsers').debug(
                'Response body:\n%s', body
            )
            return federation_response()

        self.http_get.side_effect = get
        return get_federation_token

    def run_wrap(self, keys):
        handler = self.capture_logs()
        session, sts = make_session(keys)
        sts.get_federation_token.side_effect = self.simulate_library_logs()
        url, warning = signin.wrap(
            session,
            DESTINATION,
            'aws',
            'us-west-2',
            AccountResolver(session, 'us-west-2'),
        )
        self.assertIsNone(warning)
        self.assertIsInstance(url, signin.SigninUrl)
        return handler

    def test_temporary_credentials(self):
        handler = self.run_wrap(TEMP_KEYS)
        self.assert_no_secrets(handler.records, secrets_of(TEMP_KEYS))
        self.assertIn(
            f'{signin.__name__} Console sign-in credentials from provider: '
            'env',
            handler.records,
        )
        self.assertIn(
            f'{signin.__name__} Console sign-in applied', handler.records
        )

    def test_long_term_keys(self):
        handler = self.run_wrap(LONG_KEYS)
        self.assert_no_secrets(
            handler.records, secrets_of(LONG_KEYS, FED_KEYS)
        )

    def test_filters_are_removed_afterwards(self):
        handler = self.run_wrap(TEMP_KEYS)
        logging.getLogger('urllib3.connectionpool').debug('getSigninToken')
        self.assertEqual(
            handler.records[-1], 'urllib3.connectionpool getSigninToken'
        )
        self.assertEqual(handler.filters, [])

    def test_failure_paths(self):
        handler = self.capture_logs()

        def fail(session, url):
            logging.getLogger('urllib3.connectionpool').debug('GET %s', url)
            raise EndpointConnectionError(endpoint_url=url)

        self.http_get.side_effect = fail
        session, _ = make_session(TEMP_KEYS)
        url, warning = signin.wrap(
            session,
            DESTINATION,
            'aws',
            'us-west-2',
            AccountResolver(session, 'us-west-2'),
        )
        self.assertEqual(url, DESTINATION)
        self.assert_no_secrets(
            handler.records + [warning], secrets_of(TEMP_KEYS)
        )


class TestHttpGet(unittest.TestCase):
    URL = 'https://signin.aws.amazon.com/federation?Action=getSigninToken'

    def call(self, ca_bundle):
        session = mock.Mock()
        session.get_config_variable.return_value = ca_bundle
        with (
            mock.patch.object(signin, 'URLLib3Session') as http_cls,
            mock.patch.object(
                signin, 'get_environ_proxies', return_value={'https': 'proxy'}
            ) as proxies,
        ):
            http = http_cls.return_value
            http.send.return_value = mock.Mock(status_code=200, text='{}')
            result = signin._http_get(session, self.URL)
        session.get_config_variable.assert_called_once_with('ca_bundle')
        proxies.assert_called_once_with(self.URL)
        request = http.send.call_args[0][0]
        self.assertEqual((request.method, request.url), ('GET', self.URL))
        http.close.assert_called_once_with()
        return result, http_cls

    def test_default_verify(self):
        result, http_cls = self.call(None)
        self.assertEqual(result, (200, '{}'))
        http_cls.assert_called_once_with(
            verify=True, proxies={'https': 'proxy'}, timeout=25
        )

    def test_ca_bundle(self):
        _, http_cls = self.call('/path/to/bundle')
        http_cls.assert_called_once_with(
            verify='/path/to/bundle', proxies={'https': 'proxy'}, timeout=25
        )

    def test_blank_ca_bundle_raises_without_a_request(self):
        for ca_bundle in ('', ' ', False):
            with self.subTest(ca_bundle=ca_bundle):
                session = mock.Mock()
                session.get_config_variable.return_value = ca_bundle
                with mock.patch.object(signin, 'URLLib3Session') as http_cls:
                    with self.assertRaises(signin.SigninError) as cm:
                        signin._http_get(session, self.URL)
                self.assertEqual(
                    cm.exception.reason, 'invalid ca_bundle configuration'
                )
                http_cls.assert_not_called()
