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
import argparse
import io
import logging

from awscli.customizations.open_the_console_to_this import (
    db,
    docs,
    open_console,
)
from awscli.testutils import mock, unittest

PKG = 'awscli.customizations.open_the_console_to_this'
ACCOUNT = '123456789012'
SIGNIN_URL = (
    'https://signin.aws.amazon.com/federation?Action=login'
    '&Issuer=open-the-console-to-this&SigninToken=secret-token'
)
S3_DOCS = 'https://docs.aws.amazon.com/s3/'
LS_DOCS = 'https://docs.aws.amazon.com/cli/latest/reference/s3/ls.html'
LAMBDA_DOCS = 'https://docs.aws.amazon.com/lambda/'
GET_FUNCTION_DOCS = (
    'https://docs.aws.amazon.com/cli/latest/reference/lambda/'
    'get-function.html'
)


def node(path, best, docs_best, children=None, **extra):
    data = {
        'path': path,
        'name': path.rsplit('.', 1)[-1],
        'url': {'best': best, 'source': 'curated'},
        'docs': {'best': docs_best},
        'children': children or {},
    }
    data.update(extra)
    return data


ROOT = node(
    'aws',
    'https://{host}/console/home?region={region}',
    docs.DOCS_HOME,
    {
        's3': node(
            'aws.s3',
            'https://{host}/s3/home?region={region}',
            S3_DOCS,
            {
                'ls': node(
                    'aws.s3.ls',
                    'https://{host}/s3/buckets?region={region}',
                    LS_DOCS,
                    intent={'verb': 'list'},
                    positional=['paths'],
                    flags=['recursive'],
                    scalars=['page-size'],
                ),
            },
        ),
        'lambda': node(
            'aws.lambda',
            'https://{host}/lambda/home?region={region}',
            LAMBDA_DOCS,
            {
                'get-function': node(
                    'aws.lambda.get-function',
                    'https://{host}/lambda/home?region={region}#/functions',
                    GET_FUNCTION_DOCS,
                    intent={'verb': 'view', 'id_args': ['--function-name']},
                    url={
                        'best': 'https://{host}/lambda/home#/functions',
                        'with_id': (
                            'https://{host}/lambda/home#/functions/{id:raw}'
                        ),
                        'source': 'curated',
                    },
                ),
            },
        ),
        'iam': node(
            'aws.iam',
            'https://{host}/iam/home?account={account}',
            'https://docs.aws.amazon.com/iam/',
        ),
    },
)


class FakeSession:
    def __init__(self, region='us-west-2', partition='aws'):
        self.region = region
        self.partition = partition
        self.get_credentials = mock.Mock()
        self.create_client = mock.Mock()

    def get_config_variable(self, name):
        if name == 'region':
            return self.region
        return None

    def get_scoped_config(self):
        return {}

    def get_component(self, name):
        resolver = mock.Mock()
        resolver.get_partition_for_region.return_value = self.partition
        return resolver


class BaseOpenConsoleTest(unittest.TestCase):
    def setUp(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.session = FakeSession()
        self.load_db = mock.Mock(return_value={'schema': 1, 'root': ROOT})
        self.wrap = mock.Mock(side_effect=lambda s, d, *a: (SIGNIN_URL, None))
        patchers = [
            mock.patch('sys.stdout', self.stdout),
            mock.patch('sys.stderr', self.stderr),
            mock.patch.dict('os.environ', {'DISPLAY': ':0'}, clear=True),
            mock.patch('sys.platform', 'linux'),
            mock.patch(f'{PKG}.db.load_db', self.load_db),
            mock.patch(f'{PKG}.signin.wrap', self.wrap),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        open_patcher = mock.patch('webbrowser.open_new_tab', return_value=True)
        self.open_browser = open_patcher.start()
        self.addCleanup(open_patcher.stop)

    def run_open_console(self, command, *remaining):
        parsed_args = argparse.Namespace(command=command, in_console=True)
        return open_console(self.session, parsed_args, list(remaining))


class TestHelp(BaseOpenConsoleTest):
    def assert_docs(self, url, command, *remaining):
        rc = self.run_open_console(command, *remaining)
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), url + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.open_browser.assert_called_once_with(url)
        self.assertFalse(self.wrap.called)
        self.assertFalse(self.session.get_credentials.called)
        self.assertFalse(self.session.create_client.called)

    def test_aws_help(self):
        self.assert_docs(docs.DOCS_HOME, 'help')

    def test_help_topic(self):
        self.assert_docs(
            'https://docs.aws.amazon.com/cli/latest/topic/config-vars.html',
            'help',
            'config-vars',
        )

    def test_help_topics_index(self):
        self.assert_docs(
            'https://docs.aws.amazon.com/cli/latest/topic/index.html',
            'help',
            'topics',
        )

    def test_service_help(self):
        self.assert_docs(S3_DOCS, 's3', 'help')

    def test_subcommand_help(self):
        self.assert_docs(LS_DOCS, 's3', 'ls', 'help')

    def test_help_token_after_arguments(self):
        self.assert_docs(LS_DOCS, 's3', 'ls', 's3://bucket', 'help')

    def test_help_after_a_flag_is_a_positional(self):
        self.assert_docs(LS_DOCS, 's3', 'ls', '--recursive', 'help')

    def test_option_value_named_help_is_not_help(self):
        self.assert_console(
            'https://console.aws.amazon.com/lambda/home#/functions/help',
            'lambda',
            'get-function',
            '--function-name',
            'help',
        )

    def test_scalar_option_value_named_help_is_not_help(self):
        self.assert_console(
            'https://console.aws.amazon.com/s3/buckets?region=us-west-2',
            's3',
            'ls',
            '--page-size',
            'help',
        )

    def assert_console(self, url, command, *remaining):
        rc = self.run_open_console(command, *remaining)
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), url + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.wrap.assert_called_once()
        self.assertEqual(self.wrap.call_args[0][1], url)
        self.open_browser.assert_called_once_with(SIGNIN_URL)

    def test_help_print_only(self):
        with mock.patch.dict('os.environ', {'AWS_IN_CONSOLE_OPEN': 'no'}):
            rc = self.run_open_console('s3', 'help')
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), S3_DOCS + '\n')
        self.assertFalse(self.open_browser.called)


class TestDatabaseErrors(BaseOpenConsoleTest):
    def assert_db_error(self, error, text):
        self.load_db.side_effect = error
        rc = self.run_open_console('s3', 'ls')
        self.assertEqual(rc, 255)
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(
            self.stderr.getvalue(),
            f'Unable to load the console URL database: {db.DB_PATH}: '
            f'{text}\n',
        )
        self.assertFalse(self.open_browser.called)
        self.assertFalse(self.wrap.called)

    def test_missing_file(self):
        self.assert_db_error(FileNotFoundError('missing'), 'missing')

    def test_invalid_json(self):
        self.assert_db_error(ValueError('bad json'), 'bad json')

    def test_help_also_needs_the_database(self):
        self.load_db.side_effect = OSError('denied')
        self.assertEqual(self.run_open_console('help'), 255)


class TestOpenConsole(BaseOpenConsoleTest):
    def test_signed_in_url_goes_to_browser_console_url_to_stdout(self):
        rc = self.run_open_console('s3', 'ls')
        url = 'https://console.aws.amazon.com/s3/buckets?region=us-west-2'
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), url + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.open_browser.assert_called_once_with(SIGNIN_URL)
        session, destination, partition, region, resolver = (
            self.wrap.call_args[0]
        )
        self.assertIs(session, self.session)
        self.assertEqual(destination, url)
        self.assertEqual((partition, region), ('aws', 'us-west-2'))

    def test_print_only_prints_signin_url(self):
        with mock.patch.dict('os.environ', {'AWS_IN_CONSOLE_OPEN': 'false'}):
            self.run_open_console('s3', 'ls')
        self.assertEqual(self.stdout.getvalue(), SIGNIN_URL + '\n')
        self.assertFalse(self.open_browser.called)

    def test_default_region_is_us_east_1(self):
        self.session.region = None
        with self.assertLogs(PKG, 'DEBUG') as logs:
            self.run_open_console('s3')
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.aws.amazon.com/s3/home?region=us-east-1\n',
        )
        self.assertEqual(self.wrap.call_args[0][3], 'us-east-1')
        self.assertIn('no region configured', '\n'.join(logs.output))

    def test_partition_from_region(self):
        self.session = FakeSession('cn-north-1', 'aws-cn')
        self.run_open_console('s3')
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.amazonaws.cn/s3/home?region=cn-north-1\n',
        )
        self.assertEqual(self.wrap.call_args[0][2], 'aws-cn')

    def test_warning_goes_to_stderr_and_plain_url_is_opened(self):
        warning = (
            'Unable to locate credentials. Opening the console without '
            'signing in.'
        )
        self.wrap.side_effect = lambda s, d, *a: (d, warning)
        rc = self.run_open_console('s3', 'ls')
        url = 'https://console.aws.amazon.com/s3/buckets?region=us-west-2'
        self.assertEqual(rc, 0)
        self.assertEqual(self.stderr.getvalue(), warning + '\n')
        self.assertEqual(self.stdout.getvalue(), url + '\n')
        self.open_browser.assert_called_once_with(url)

    def test_unknown_command_uses_go_view(self):
        self.run_open_console('not-a-service', 'do-thing')
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.aws.amazon.com/go/view?service=not-a-service'
            '&region=us-west-2\n',
        )

    def test_one_account_resolver_shared_by_resolver_and_signin(self):
        with mock.patch(f'{PKG}.account.AccountResolver') as account_cls:
            account_cls.return_value.get.return_value = ACCOUNT
            self.run_open_console('iam')
        account_cls.assert_called_once_with(self.session, 'us-west-2')
        self.assertIs(self.wrap.call_args[0][4], account_cls.return_value)
        self.assertEqual(
            self.stdout.getvalue(),
            f'https://console.aws.amazon.com/iam/home?account={ACCOUNT}\n',
        )

    def test_account_is_not_looked_up_when_not_needed(self):
        with mock.patch(f'{PKG}.account.AccountResolver') as account_cls:
            self.run_open_console('s3', 'ls')
        self.assertFalse(account_cls.return_value.get.called)

    def test_debug_log_has_decision_but_no_signin_url(self):
        self.session.get_credentials.return_value = mock.Mock(method='env')
        with self.assertLogs(PKG, 'DEBUG') as logs:
            self.run_open_console('s3', 'ls')
        output = '\n'.join(logs.output)
        self.assertIn('node=aws.s3.ls', output)
        self.assertIn('source=curated', output)
        self.assertIn('verb=list', output)
        self.assertIn('sign-in applied=True', output)
        self.assertIn('credential method=env', output)
        self.assertNotIn('secret-token', output)
        self.assertNotIn('SigninToken', output)

    def test_no_credentials_does_not_resolve_credentials_again(self):
        self.wrap.side_effect = lambda s, d, *a: (
            d,
            'Unable to locate credentials. Opening the console without '
            'signing in.',
        )
        with self.assertLogs(PKG, logging.DEBUG) as logs:
            self.run_open_console('s3', 'ls')
        self.assertFalse(self.session.get_credentials.called)
        self.assertIn('sign-in applied=False', '\n'.join(logs.output))
