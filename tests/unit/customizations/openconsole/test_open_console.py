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
import argparse
import io
import logging

from awscli.customizations.openconsole import (
    ConsoleOpener,
    docs,
    open_console,
    signin,
)
from awscli.testutils import mock, unittest

PKG = 'awscli.customizations.openconsole'
SIGNIN = signin.SigninUrl(
    'signin.aws.amazon.com', 'https://console.aws.amazon.com/', 'secret-token'
)
# What the browser is given.
SIGNIN_URL = SIGNIN.unhashed()
TOKEN_HASH = signin.hashed('secret-token')
S3_DOCS = 'https://docs.aws.amazon.com/s3/'
LS_DOCS = 'https://docs.aws.amazon.com/cli/latest/reference/s3/ls.html'


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
        self.wrap = mock.Mock(side_effect=lambda s, d, *a: (SIGNIN, None))
        patchers = [
            mock.patch('sys.stdout', self.stdout),
            mock.patch('sys.stderr', self.stderr),
            mock.patch.dict('os.environ', {'DISPLAY': ':0'}, clear=True),
            mock.patch('sys.platform', 'linux'),
            mock.patch(f'{PKG}.signin.wrap', self.wrap),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        open_patcher = mock.patch('webbrowser.open_new_tab', return_value=True)
        self.open_browser = open_patcher.start()
        self.addCleanup(open_patcher.stop)

    def run_open_console(self, command, *remaining):
        parsed_args = argparse.Namespace(command=command, console_link=True)
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
            'https://us-west-2.console.aws.amazon.com/lambda/home'
            '?region=us-west-2#/functions/help',
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

    def test_print_only_prints_console_url_and_does_not_sign_in(self):
        with mock.patch.dict('os.environ', {'AWS_IN_CONSOLE_OPEN': 'false'}):
            with self.assertLogs(PKG, 'DEBUG') as logs:
                rc = self.run_open_console('s3', 'ls')
        url = 'https://console.aws.amazon.com/s3/buckets?region=us-west-2'
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), url + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.assertFalse(self.wrap.called)
        self.assertFalse(self.session.get_credentials.called)
        self.assertFalse(self.open_browser.called)
        self.assertIn(
            'sign-in not attempted in print-only mode', '\n'.join(logs.output)
        )

    def test_default_region_is_us_east_1(self):
        self.session.region = None
        with self.assertLogs(PKG, 'DEBUG') as logs:
            self.run_open_console('s3')
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.aws.amazon.com/s3/buckets?region=us-east-1\n',
        )
        self.assertEqual(self.wrap.call_args[0][3], 'us-east-1')
        self.assertIn('no region configured', '\n'.join(logs.output))

    def test_partition_from_region(self):
        self.session = FakeSession('cn-north-1', 'aws-cn')
        self.run_open_console('s3')
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.amazonaws.cn/s3/buckets?region=cn-north-1\n',
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

    def test_account_resolver_is_given_to_sign_in(self):
        with mock.patch(f'{PKG}.account.AccountResolver') as account_cls:
            self.run_open_console('iam')
        account_cls.assert_called_once_with(self.session, 'us-west-2')
        self.assertIs(self.wrap.call_args[0][4], account_cls.return_value)
        self.assertEqual(
            self.stdout.getvalue(),
            'https://console.aws.amazon.com/iam/home\n',
        )
        self.assertFalse(account_cls.return_value.caller_arn.called)

    def test_debug_log_has_decision_but_no_signin_url(self):
        self.session.get_credentials.return_value = mock.Mock(method='env')
        with self.assertLogs(PKG, 'DEBUG') as logs:
            self.run_open_console('s3', 'ls')
        output = '\n'.join(logs.output)
        self.assertIn('node=aws.s3.ls', output)
        self.assertIn('source=console', output)
        self.assertIn('verb=list', output)
        self.assertIn('explanation=aws.s3.ls: opened the bucket list.', output)
        self.assertIn('sign-in applied=True', output)
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


class TestConsoleOpener(BaseOpenConsoleTest):
    URL = 'https://console.aws.amazon.com/s3/buckets?region=us-west-2'

    def open(self):
        ConsoleOpener(self.session, 's3', ['ls']).open(None)

    def test_opens_the_signin_url_and_prints_nothing(self):
        self.open()
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(self.stderr.getvalue(), '')
        self.assertEqual(self.wrap.call_args[0][1], self.URL)
        self.open_browser.assert_called_once_with(SIGNIN_URL)

    def test_print_only_prints_console_url_and_does_not_sign_in(self):
        with mock.patch.dict('os.environ', {'AWS_IN_CONSOLE_OPEN': 'false'}):
            self.open()
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(self.stderr.getvalue(), self.URL + '\n')
        self.assertFalse(self.wrap.called)
        self.assertFalse(self.open_browser.called)

    def test_error_quoting_the_signin_url_has_the_token_hashed(self):
        error = RuntimeError(f'cannot hand over {SIGNIN_URL}')
        with mock.patch(
            f'{PKG}.browser.open_beside_output', side_effect=error
        ):
            with self.assertLogs(PKG, 'DEBUG') as logs:
                self.open()
        self.assertEqual(
            self.stderr.getvalue(),
            f'Could not open the console (cannot hand over {SIGNIN}).\n',
        )
        output = '\n'.join(logs.output)
        self.assertIn('Console: opening failed', output)
        self.assertIn(f'RuntimeError: cannot hand over {SIGNIN}', output)
        self.assertIn(f'SigninToken={TOKEN_HASH}', output)
        for text in (output, self.stderr.getvalue(), self.stdout.getvalue()):
            self.assertNotIn('secret-token', text)

    def test_error_before_sign_in_is_reported_unchanged(self):
        with mock.patch(
            f'{PKG}.resolver.resolve', side_effect=ValueError('bad json')
        ):
            self.open()
        self.assertEqual(
            self.stderr.getvalue(), 'Could not open the console (bad json).\n'
        )
        self.assertFalse(self.wrap.called)
        self.assertFalse(self.open_browser.called)

    def test_error_without_message_uses_its_type(self):
        with mock.patch(f'{PKG}.resolver.resolve', side_effect=ValueError()):
            self.open()
        self.assertEqual(
            self.stderr.getvalue(),
            'Could not open the console (ValueError).\n',
        )


class TestRunAndOpen(unittest.TestCase):
    def run_and_open(self, command, remaining, rc=0):
        from awscli.customizations.openconsole import (
            run_and_open,
        )

        parsed_args = argparse.Namespace(command=command, open_console=True)
        callable_ = mock.Mock(return_value=rc)
        with mock.patch(f'{PKG}.ConsoleOpener.open') as opener_open:
            result = run_and_open(
                mock.Mock(), parsed_args, remaining, callable_
            )
        callable_.assert_called_once_with(remaining, parsed_args)
        return result, parsed_args, opener_open

    def test_help_only_shows_help(self):
        for command, remaining in (('help', []), ('s3', ['ls', 'help'])):
            with self.subTest(command=command, remaining=remaining):
                rc, parsed_args, opener_open = self.run_and_open(
                    command, remaining
                )
                self.assertEqual(rc, 0)
                self.assertFalse(hasattr(parsed_args, 'console_opener'))
                self.assertFalse(opener_open.called)

    def test_command_without_api_response_opens_afterwards(self):
        rc, parsed_args, opener_open = self.run_and_open(
            's3', ['mb', 's3://photos']
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(parsed_args.console_opener)
        opener_open.assert_called_once_with(None)

    def test_failed_command_opens_nothing(self):
        rc, _, opener_open = self.run_and_open('s3', ['mb', 's3://x'], rc=1)
        self.assertEqual(rc, 1)
        self.assertFalse(opener_open.called)

    def test_api_response_opens_after_the_command_returns(self):
        from awscli.customizations.openconsole import (
            run_and_open,
        )

        parsed_args = argparse.Namespace(command='s3', open_console=True)
        response = {'Buckets': []}
        order = []

        def command(remaining, args):
            order.append('command')
            shown = args.console_opener.before_display(response)
            self.assertIs(shown, response)
            order.append('displayed')
            return 0

        def record(captured):
            order.append('open')
            self.assertIs(captured, response)

        with mock.patch(f'{PKG}.ConsoleOpener.open', side_effect=record):
            rc = run_and_open(mock.Mock(), parsed_args, ['ls'], command)
        self.assertEqual(rc, 0)
        self.assertEqual(order, ['command', 'displayed', 'open'])
