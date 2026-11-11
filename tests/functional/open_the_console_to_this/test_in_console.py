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
import json
import os
import shutil
import tempfile
from urllib.parse import quote_plus

from awscli.clidriver import AWSCLIEntryPoint, create_clidriver
from awscli.customizations.open_the_console_to_this import docs, signin
from tests.functional.open_the_console_to_this.support import (
    ACCOUNT,
    FEDERATION_RESPONSE,
    LOGIN_PREFIX,
    SIGNIN_TOKEN,
    ConsoleCommandTest,
)

S3_BUCKETS_US_EAST_1 = (
    'https://console.aws.amazon.com/s3/buckets?region=us-east-1'
)
EC2_INSTANCE_US_WEST_2 = (
    'https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2'
    '#InstanceDetails:instanceId=i-0123456789abcdef0'
)
NO_CREDENTIALS_WARNING = (
    'Unable to locate credentials. Opening the console without signing in.\n'
)


class TestInConsole(ConsoleCommandTest):
    def setUp(self):
        super().setUp()
        self.parsed_response = FEDERATION_RESPONSE
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

    def write_file(self, name, contents=''):
        path = os.path.join(self.tempdir, name)
        with open(path, 'w') as f:
            f.write(contents)
        return path

    def use_config(self, contents):
        # The session reads the config file once, so start a new driver.
        self.environ['AWS_CONFIG_FILE'] = self.write_file('config', contents)
        self.driver = create_clidriver()
        self.entry_point = AWSCLIEntryPoint(self.driver)

    def assert_signed_in(self, destination):
        query = super().assert_signed_in(destination)
        self.assertEqual(query['SigninToken'], ['tok'])
        self.assertEqual(query['Issuer'], [signin.ISSUER])
        self.http_get.assert_called_once()

    def assert_docs(self, cmd, url):
        stdout, stderr, _ = self.run_cmd(cmd)
        self.assertEqual(stdout, url + '\n')
        self.assertEqual(stderr, '')
        self.assertEqual(self.operations_called, [])
        self.assertFalse(self.http_get.called)
        self.open_browser.assert_called_once_with(url)

    def test_s3_ls_long_term_keys(self):
        stdout, stderr, rc = self.run_cmd('s3 ls --console-link')
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertEqual(stderr, '')
        self.assertEqual(self.operation_names(), ['GetFederationToken'])
        params = self.operations_called[0][1]
        self.assertEqual(params['Name'], signin.ISSUER)
        self.assertEqual(params['DurationSeconds'], 3600)
        self.assert_signed_in(S3_BUCKETS_US_EAST_1)
        # The sign-in token is requested with the federated credentials.
        token_url = self.http_get.call_args[0][1]
        self.assertIn('getSigninToken', token_url)
        self.assertIn('ASIAFEDERATED0000001', token_url)
        self.assertNotIn('secret_key', token_url)

    def test_flag_before_the_command(self):
        stdout, _, _ = self.run_cmd('--console-link s3 ls')
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assert_signed_in(S3_BUCKETS_US_EAST_1)

    def test_ec2_detail_page_on_regional_host(self):
        stdout, _, _ = self.run_cmd(
            'ec2 describe-instances --instance-ids i-0123456789abcdef0 '
            '--console-link --region us-west-2'
        )
        self.assertEqual(stdout, EC2_INSTANCE_US_WEST_2 + '\n')
        self.assertEqual(self.operation_names(), ['GetFederationToken'])
        self.assert_signed_in(EC2_INSTANCE_US_WEST_2)

    def test_flag_between_service_and_operation(self):
        stdout, _, _ = self.run_cmd(
            'ec2 --console-link describe-instances --region us-west-2 '
            '--instance-ids i-0123456789abcdef0'
        )
        self.assertEqual(stdout, EC2_INSTANCE_US_WEST_2 + '\n')

    def test_temporary_role_credentials_skip_get_federation_token(self):
        self.environ['AWS_SESSION_TOKEN'] = 'session_token'
        self.parsed_response = {
            'Account': ACCOUNT,
            'Arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/Admin/me',
        }
        stdout, stderr, _ = self.run_cmd('s3 ls --console-link')
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertEqual(stderr, '')
        self.assertEqual(self.operation_names(), ['GetCallerIdentity'])
        self.assert_signed_in(S3_BUCKETS_US_EAST_1)
        self.assertIn('session_token', self.http_get.call_args[0][1])

    def test_root_session_credentials_open_plain_url_with_warning(self):
        self.environ['AWS_SESSION_TOKEN'] = 'session_token'
        self.parsed_response = {
            'Account': ACCOUNT,
            'Arn': f'arn:aws:iam::{ACCOUNT}:root',
        }
        stdout, stderr, rc = self.run_cmd('s3 ls --console-link')
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertEqual(
            stderr,
            'Console sign-in failed (root user session credentials cannot '
            'sign in to the console through federation; only role and '
            'federated user sessions can). Opening the console without '
            'signing in.\n',
        )
        self.assertEqual(self.operation_names(), ['GetCallerIdentity'])
        self.assertFalse(self.http_get.called)
        self.open_browser.assert_called_once_with(S3_BUCKETS_US_EAST_1)

    def test_no_credentials_opens_plain_url_with_warning(self):
        for name in (
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY',
            'AWS_SESSION_TOKEN',
        ):
            self.environ.pop(name, None)
        self.environ['AWS_SHARED_CREDENTIALS_FILE'] = self.write_file(
            'credentials'
        )
        self.use_config('')
        # Keep the instance metadata provider from reaching the network.
        self.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
        stdout, stderr, rc = self.run_cmd('s3 ls --console-link')
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, NO_CREDENTIALS_WARNING)
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertEqual(self.operations_called, [])
        self.assertFalse(self.http_get.called)
        self.open_browser.assert_called_once_with(S3_BUCKETS_US_EAST_1)

    def test_aws_help(self):
        self.assert_docs('help --console-link', docs.DOCS_HOME)

    def test_service_help(self):
        self.assert_docs(
            's3 help --console-link', 'https://docs.aws.amazon.com/s3/'
        )

    def test_subcommand_help(self):
        self.assert_docs(
            's3 ls help --console-link',
            'https://docs.aws.amazon.com/cli/latest/reference/s3/ls.html',
        )

    def test_help_topics(self):
        self.assert_docs(
            'help topics --console-link',
            'https://docs.aws.amazon.com/cli/latest/topic/index.html',
        )

    def test_flag_first_with_help(self):
        self.assert_docs('--console-link help', docs.DOCS_HOME)

    def test_function_named_help_opens_the_function_page(self):
        url = (
            'https://us-west-2.console.aws.amazon.com/lambda/home'
            '?region=us-west-2#/functions/help'
        )
        stdout, stderr, rc = self.run_cmd(
            'lambda get-function --function-name help --console-link '
            '--region us-west-2'
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, url + '\n')
        self.assertEqual(stderr, '')
        self.assert_signed_in(url)

    def test_print_only_env_var_prints_console_url_without_signing_in(self):
        self.environ['AWS_IN_CONSOLE_OPEN'] = 'false'
        stdout, stderr, rc = self.run_cmd('s3 ls --console-link')
        self.assertEqual(rc, 0)
        self.assertFalse(self.open_browser.called)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertEqual(self.operations_called, [])
        self.assertFalse(self.http_get.called)

    def test_print_only_config_setting(self):
        self.use_config('[default]\nin_console_open = off\n')
        stdout, _, _ = self.run_cmd('s3 ls --console-link')
        self.assertFalse(self.open_browser.called)
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        self.assertFalse(self.http_get.called)

    def test_browser_error_shows_the_signin_token_hashed(self):
        self.http_get.return_value = (
            200,
            json.dumps({'SigninToken': SIGNIN_TOKEN}),
        )

        def fail(url):
            raise RuntimeError(f'no handler for {url}')

        self.open_browser.side_effect = fail
        stdout, stderr, rc = self.run_cmd('s3 ls --console-link')
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, S3_BUCKETS_US_EAST_1 + '\n')
        hashed_url = (
            f'{LOGIN_PREFIX}Issuer={signin.ISSUER}'
            f'&Destination={quote_plus(S3_BUCKETS_US_EAST_1)}'
            f'&SigninToken={signin.hashed(SIGNIN_TOKEN)}'
        )
        self.assertEqual(
            stderr,
            f'Could not open a browser (no handler for {hashed_url}); the '
            'URL is printed above.\n',
        )
        for secret in (SIGNIN_TOKEN, quote_plus(SIGNIN_TOKEN)):
            self.assertNotIn(secret, stdout + stderr)

    def test_region_from_profile(self):
        self.environ.pop('AWS_DEFAULT_REGION', None)
        self.use_config(
            '[profile prod]\n'
            'region = eu-west-2\n'
            'aws_access_key_id = AKIDPROFILEKEY\n'
            'aws_secret_access_key = profile-secret\n',
        )
        stdout, _, _ = self.run_cmd('--profile prod s3 ls --console-link')
        url = 'https://console.aws.amazon.com/s3/buckets?region=eu-west-2'
        self.assertEqual(stdout, url + '\n')
        self.assertEqual(self.operation_names(), ['GetFederationToken'])
        self.assert_signed_in(url)

    def test_unknown_subcommand_uses_the_service_page(self):
        stdout, _, _ = self.run_cmd('s3 not-a-subcommand --console-link')
        self.assertEqual(
            stdout,
            'https://console.aws.amazon.com/s3/buckets?region=us-east-1\n',
        )

    def test_service_without_a_built_in_page_uses_go_view(self):
        stdout, _, _ = self.run_cmd(
            'sts get-caller-identity --console-link'
        )
        self.assertEqual(
            stdout,
            'https://console.aws.amazon.com/go/view?service=sts'
            '&region=us-east-1\n',
        )

    def test_without_the_flag_the_command_runs(self):
        self.parsed_response = {'Buckets': []}
        self.run_cmd('s3 ls')
        self.assertEqual(self.operation_names(), ['ListBuckets'])
        self.assertFalse(self.open_browser.called)
        self.assertFalse(self.http_get.called)
