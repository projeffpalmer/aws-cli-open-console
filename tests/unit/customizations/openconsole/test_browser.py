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
import io
import os
import webbrowser

from awscli.customizations.openconsole import browser
from awscli.customizations.openconsole.signin import (
    SigninUrl,
    hashed,
)
from awscli.testutils import mock, unittest

CONSOLE_URL = 'https://console.aws.amazon.com/s3/buckets?region=us-east-1'
SIGNIN = SigninUrl('signin.aws.amazon.com', CONSOLE_URL, 'secret-token')
# What the browser is given, and what a message shows in its place.
SIGNIN_URL = SIGNIN.unhashed()
HASHED_SIGNIN_URL = str(SIGNIN)
TOKEN_HASH = hashed('secret-token')
OPEN = 'webbrowser.open_new_tab'
NO_BROWSER_WARNING = (
    'Could not open a browser (no runnable browser found); the URL is '
    'printed above.\n'
)


def make_session(scoped_config=None):
    session = mock.Mock()
    session.get_scoped_config.return_value = scoped_config or {}
    return session


class TestPrintOnly(unittest.TestCase):
    def assert_print_only(self, expected, environ, platform='darwin', **cfg):
        with mock.patch.dict('os.environ', environ, clear=True):
            with mock.patch('sys.platform', platform):
                self.assertIs(browser.print_only(make_session(cfg)), expected)

    def test_opens_by_default_with_a_display(self):
        self.assert_print_only(False, {'DISPLAY': ':0'}, 'linux')

    def test_opens_by_default_on_macos_and_windows(self):
        self.assert_print_only(False, {}, 'darwin')
        self.assert_print_only(False, {}, 'win32')

    def test_env_var_false_values(self):
        for value in ('false', 'FALSE', '0', 'no', 'No', 'off', ' Off '):
            with self.subTest(value=value):
                self.assert_print_only(True, {'AWS_CLI_CONSOLE_OPEN': value})

    def test_env_var_true_values_do_not_print_only(self):
        for value in ('true', '1', 'yes', 'on', ''):
            with self.subTest(value=value):
                self.assert_print_only(False, {'AWS_CLI_CONSOLE_OPEN': value})

    def test_config_false_values(self):
        for value in ('false', 'False', '0', 'no', 'off'):
            with self.subTest(value=value):
                self.assert_print_only(True, {}, cli_console_open=value)

    def test_config_true_does_not_print_only(self):
        self.assert_print_only(False, {}, cli_console_open='true')

    def test_config_read_error_is_ignored(self):
        session = make_session()
        session.get_scoped_config.side_effect = Exception('no profile')
        with mock.patch.dict('os.environ', {}, clear=True):
            with mock.patch('sys.platform', 'darwin'):
                self.assertFalse(browser.print_only(session))

    def test_headless_unix_platforms_print_only(self):
        for platform in ('linux', 'freebsd13', 'openbsd7', 'netbsd9'):
            with self.subTest(platform=platform):
                self.assert_print_only(True, {}, platform)

    def test_wayland_display_counts_as_a_display(self):
        self.assert_print_only(
            False, {'WAYLAND_DISPLAY': 'wayland-0'}, 'linux'
        )

    def test_empty_display_is_no_display(self):
        self.assert_print_only(True, {'DISPLAY': ''}, 'linux')


class TestDeliver(unittest.TestCase):
    def setUp(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        patchers = [
            mock.patch('sys.stdout', self.stdout),
            mock.patch('sys.stderr', self.stderr),
            mock.patch.dict('os.environ', {'DISPLAY': ':0'}, clear=True),
            mock.patch('sys.platform', 'linux'),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        open_patcher = mock.patch(OPEN, return_value=True)
        self.open_browser = open_patcher.start()
        self.addCleanup(open_patcher.stop)

    def test_prints_console_url_and_opens_signin_url(self):
        rc = browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.open_browser.assert_called_once_with(SIGNIN_URL)

    def test_print_only_prints_the_console_url_not_the_signin_url(self):
        session = make_session({'cli_console_open': 'false'})
        rc = browser.deliver(CONSOLE_URL, SIGNIN, session)
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertEqual(self.stderr.getvalue(), '')
        self.assertFalse(self.open_browser.called)

    def test_print_only_without_signin_prints_console_url(self):
        session = make_session({'cli_console_open': 'off'})
        browser.deliver(CONSOLE_URL, CONSOLE_URL, session)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertFalse(self.open_browser.called)

    def test_opens_inside_original_ld_library_path(self):
        environ = {}

        def open_new_tab(url):
            environ.update(os.environ)
            return True

        self.open_browser.side_effect = open_new_tab
        with mock.patch.dict(
            'os.environ', {'LD_LIBRARY_PATH': '/bundle'}, clear=False
        ):
            browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertNotIn('LD_LIBRARY_PATH', environ)
        self.assertEqual(environ.get('PYINSTALLER_RESET_ENVIRONMENT'), '1')

    def test_no_runnable_browser_warns_and_succeeds(self):
        self.open_browser.return_value = False
        rc = browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertEqual(self.stderr.getvalue(), NO_BROWSER_WARNING)
        self.open_browser.assert_called_once_with(SIGNIN_URL)

    def test_no_runnable_browser_warning_does_not_leak_the_signin_url(self):
        self.open_browser.return_value = False
        with self.assertLogs(browser.LOG.name, 'DEBUG') as logs:
            browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertNotIn('secret-token', self.stderr.getvalue())
        self.assertNotIn(SIGNIN_URL, self.stderr.getvalue())
        self.assertNotIn('secret-token', '\n'.join(logs.output))

    def test_browser_error_warns_and_succeeds(self):
        self.open_browser.side_effect = webbrowser.Error('no runnable browser')
        rc = browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertEqual(
            self.stderr.getvalue(),
            'Could not open a browser (no runnable browser); the URL is '
            'printed above.\n',
        )

    def test_os_error_warning_has_the_signin_token_hashed(self):
        self.open_browser.side_effect = OSError(f'cannot run {SIGNIN_URL}')
        with self.assertLogs(browser.LOG.name, 'DEBUG') as logs:
            rc = browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(rc, 0)
        self.assertEqual(
            self.stderr.getvalue(),
            f'Could not open a browser (cannot run {HASHED_SIGNIN_URL}); '
            'the URL is printed above.\n',
        )
        self.assertIn(f'SigninToken={TOKEN_HASH}', self.stderr.getvalue())
        self.assertNotIn('secret-token', self.stderr.getvalue())
        self.assertNotIn('secret-token', '\n'.join(logs.output))
        self.assertNotIn('secret-token', self.stdout.getvalue())

    def test_unexpected_error_is_a_warning_with_the_token_hashed(self):
        self.open_browser.side_effect = RuntimeError(
            f'no handler for {SIGNIN_URL}'
        )
        with self.assertLogs(browser.LOG.name, 'DEBUG') as logs:
            rc = browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(rc, 0)
        self.assertEqual(self.stdout.getvalue(), CONSOLE_URL + '\n')
        self.assertEqual(
            self.stderr.getvalue(),
            f'Could not open a browser (no handler for {HASHED_SIGNIN_URL}); '
            'the URL is printed above.\n',
        )
        self.assertNotIn('secret-token', self.stderr.getvalue())
        self.assertNotIn('secret-token', '\n'.join(logs.output))

    def test_bare_token_in_an_error_is_hashed(self):
        self.open_browser.side_effect = OSError('bad argument secret-token')
        browser.deliver(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(
            self.stderr.getvalue(),
            f'Could not open a browser (bad argument {TOKEN_HASH}); the URL '
            'is printed above.\n',
        )

    def test_plain_url_in_an_error_is_replaced(self):
        self.open_browser.side_effect = OSError(f'cannot run {CONSOLE_URL}')
        browser.deliver(CONSOLE_URL, CONSOLE_URL, make_session())
        self.assertEqual(
            self.stderr.getvalue(),
            'Could not open a browser (cannot run <url>); the URL is '
            'printed above.\n',
        )

    def test_error_without_message_uses_its_type(self):
        self.open_browser.side_effect = OSError()
        browser.deliver(CONSOLE_URL, CONSOLE_URL, make_session())
        self.assertIn('(OSError)', self.stderr.getvalue())


class TestOpenBesideOutput(unittest.TestCase):
    setUp = TestDeliver.setUp

    def test_opens_signin_url_and_leaves_stdout_alone(self):
        browser.open_beside_output(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(self.stderr.getvalue(), '')
        self.open_browser.assert_called_once_with(SIGNIN_URL)

    def test_print_only_prints_the_console_url_on_stderr(self):
        session = make_session({'cli_console_open': 'false'})
        browser.open_beside_output(CONSOLE_URL, SIGNIN, session)
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(self.stderr.getvalue(), CONSOLE_URL + '\n')
        self.assertFalse(self.open_browser.called)

    def test_no_runnable_browser_names_the_console_page(self):
        self.open_browser.return_value = False
        browser.open_beside_output(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(
            self.stderr.getvalue(),
            'Could not open a browser (no runnable browser found); the '
            f'console page is {CONSOLE_URL}\n',
        )
        self.assertNotIn('secret-token', self.stderr.getvalue())

    def test_error_names_the_console_page_with_the_token_hashed(self):
        self.open_browser.side_effect = RuntimeError(
            f'no handler for {SIGNIN_URL}'
        )
        browser.open_beside_output(CONSOLE_URL, SIGNIN, make_session())
        self.assertEqual(self.stdout.getvalue(), '')
        self.assertEqual(
            self.stderr.getvalue(),
            f'Could not open a browser (no handler for {HASHED_SIGNIN_URL}); '
            f'the console page is {CONSOLE_URL}\n',
        )
        self.assertNotIn('secret-token', self.stderr.getvalue())
