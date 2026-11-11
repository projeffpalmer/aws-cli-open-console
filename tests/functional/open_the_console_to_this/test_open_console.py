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
import sys
from urllib.parse import quote_plus

from awscli.customizations.open_the_console_to_this import signin
from awscli.testutils import mock
from tests.functional.open_the_console_to_this.support import (
    ACCOUNT,
    FEDERATION_RESPONSE,
    LOGIN_PREFIX,
    PKG,
    SIGNIN_TOKEN,
    ConsoleCommandTest,
)

CREATE_TABLE = (
    'dynamodb create-table --table-name MusicCollection '
    '--attribute-definitions AttributeName=Artist,AttributeType=S '
    '--key-schema AttributeName=Artist,KeyType=HASH '
    '--billing-mode PAY_PER_REQUEST --region us-west-2 --open-console'
)
CREATE_TABLE_RESPONSE = {
    'TableDescription': {
        'TableName': 'MusicCollection',
        'TableStatus': 'CREATING',
        'TableArn': (
            f'arn:aws:dynamodb:us-west-2:{ACCOUNT}:table/MusicCollection'
        ),
    }
}
TABLE_PAGE = (
    'https://us-west-2.console.aws.amazon.com/dynamodbv2/home'
    '?region=us-west-2#table?name=MusicCollection'
)
EC2_HOME = (
    'https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2'
)


class TestOpenConsole(ConsoleCommandTest):
    def setUp(self):
        self.stdout_when_opened = []
        super().setUp()

    def _patch_browser(self):
        open_patcher = mock.patch(
            'webbrowser.open_new_tab', side_effect=self.record_open
        )
        self.open_browser = open_patcher.start()
        self.addCleanup(open_patcher.stop)

    def record_open(self, url):
        self.stdout_when_opened.append(sys.stdout.getvalue())
        return True

    def test_create_table_opens_the_new_table_after_the_command(self):
        self.parsed_responses = [CREATE_TABLE_RESPONSE, FEDERATION_RESPONSE]
        stdout, stderr, rc = self.run_cmd(CREATE_TABLE)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, '')
        self.assertEqual(
            json.loads(stdout)['TableDescription']['TableName'],
            'MusicCollection',
        )
        self.assertEqual(
            self.operation_names(), ['CreateTable', 'GetFederationToken']
        )
        self.assert_signed_in(TABLE_PAGE)
        self.assertEqual(self.stdout_when_opened, [stdout])

    def test_output_is_the_same_as_without_the_flag(self):
        self.parsed_responses = [CREATE_TABLE_RESPONSE, FEDERATION_RESPONSE]
        with_flag, _, _ = self.run_cmd(CREATE_TABLE)
        self.parsed_responses = [CREATE_TABLE_RESPONSE]
        without_flag, _, _ = self.run_cmd(
            CREATE_TABLE.replace(' --open-console', '')
        )
        self.assertEqual(with_flag, without_flag)
        self.open_browser.assert_called_once()

    def test_run_instances_opens_the_instance(self):
        self.parsed_responses = [
            {
                'ReservationId': 'r-1',
                'Instances': [{'InstanceId': 'i-0123456789abcdef0'}],
            },
            FEDERATION_RESPONSE,
        ]
        self.run_cmd(
            'ec2 run-instances --image-id ami-12345678 --region us-west-2 '
            '--open-console'
        )
        self.assertEqual(
            self.operation_names(), ['RunInstances', 'GetFederationToken']
        )
        self.assert_signed_in(
            EC2_HOME + '#InstanceDetails:instanceId=i-0123456789abcdef0'
        )

    def test_several_instances_open_the_instances_list(self):
        self.parsed_responses = [
            {
                'Instances': [
                    {'InstanceId': 'i-0aaaaaaaaaaaaaaaa'},
                    {'InstanceId': 'i-0bbbbbbbbbbbbbbbb'},
                ],
            },
            FEDERATION_RESPONSE,
        ]
        self.run_cmd(
            'ec2 run-instances --image-id ami-12345678 --count 2 '
            '--region us-west-2 --open-console'
        )
        self.assert_signed_in(EC2_HOME + '#Instances:')

    def test_paginated_response_is_fetched_once(self):
        self.parsed_responses = [
            {
                'Reservations': [
                    {'Instances': [{'InstanceId': 'i-0123456789abcdef0'}]}
                ]
            },
            FEDERATION_RESPONSE,
        ]
        stdout, _, _ = self.run_cmd(
            'ec2 describe-instances --region us-west-2 --open-console'
        )
        self.assertEqual(
            self.operation_names(),
            ['DescribeInstances', 'GetFederationToken'],
        )
        self.assertEqual(
            json.loads(stdout)['Reservations'][0]['Instances'][0][
                'InstanceId'
            ],
            'i-0123456789abcdef0',
        )
        self.assert_signed_in(
            EC2_HOME + '#InstanceDetails:instanceId=i-0123456789abcdef0'
        )
        self.assertEqual(self.stdout_when_opened, [stdout])

    def test_custom_command_opens_from_its_arguments(self):
        self.parsed_responses = [{}, FEDERATION_RESPONSE]
        stdout, _, _ = self.run_cmd('s3 mb s3://photos --open-console')
        self.assertEqual(
            self.operation_names(), ['CreateBucket', 'GetFederationToken']
        )
        self.assert_signed_in(
            'https://console.aws.amazon.com/s3/buckets/photos'
            '?region=us-east-1'
        )
        self.assertIn('make_bucket: photos', stdout)
        self.assertEqual(self.stdout_when_opened, [stdout])

    def test_failed_command_opens_nothing(self):
        self.parsed_responses = [
            {'Error': {'Code': 'ResourceInUseException', 'Message': 'x'}}
        ]
        self.run_cmd(CREATE_TABLE, expected_rc=254)
        self.assertEqual(self.operation_names(), ['CreateTable'])
        self.assertFalse(self.open_browser.called)
        self.assertFalse(self.http_get.called)

    def test_print_only_puts_the_console_url_on_stderr(self):
        self.environ['AWS_IN_CONSOLE_OPEN'] = 'false'
        self.parsed_responses = [CREATE_TABLE_RESPONSE]
        stdout, stderr, _ = self.run_cmd(CREATE_TABLE)
        self.assertFalse(self.open_browser.called)
        self.assertEqual(
            json.loads(stdout)['TableDescription']['TableName'],
            'MusicCollection',
        )
        self.assertEqual(stderr, TABLE_PAGE + '\n')
        self.assertEqual(self.operation_names(), ['CreateTable'])
        self.assertFalse(self.http_get.called)

    def test_browser_error_shows_the_signin_token_hashed(self):
        self.http_get.return_value = (
            200,
            json.dumps({'SigninToken': SIGNIN_TOKEN}),
        )

        def fail(url):
            raise RuntimeError(f'no handler for {url}')

        self.open_browser.side_effect = fail
        self.parsed_responses = [CREATE_TABLE_RESPONSE, FEDERATION_RESPONSE]
        stdout, stderr, rc = self.run_cmd(CREATE_TABLE)
        self.assertEqual(rc, 0)
        self.assertIn('MusicCollection', stdout)
        hashed_url = (
            f'{LOGIN_PREFIX}Issuer={signin.ISSUER}'
            f'&Destination={quote_plus(TABLE_PAGE)}'
            f'&SigninToken={signin.hashed(SIGNIN_TOKEN)}'
        )
        self.assertEqual(
            stderr,
            f'Could not open a browser (no handler for {hashed_url}); the '
            f'console page is {TABLE_PAGE}\n',
        )
        for secret in (SIGNIN_TOKEN, quote_plus(SIGNIN_TOKEN)):
            self.assertNotIn(secret, stdout + stderr)

    def test_console_link_wins_and_bypasses_the_command(self):
        self.parsed_responses = [FEDERATION_RESPONSE]
        stdout, _, _ = self.run_cmd('s3 ls --console-link --open-console')
        self.assertEqual(self.operation_names(), ['GetFederationToken'])
        self.assertEqual(
            stdout,
            'https://console.aws.amazon.com/s3/buckets?region=us-east-1\n',
        )

    def test_console_error_only_warns(self):
        self.parsed_responses = [CREATE_TABLE_RESPONSE]
        with mock.patch(
            f'{PKG}.follow.resolve_after_run', side_effect=ValueError('boom')
        ):
            stdout, stderr, rc = self.run_cmd(CREATE_TABLE)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, 'Could not open the console (boom).\n')
        self.assertIn('MusicCollection', stdout)
        self.assertFalse(self.open_browser.called)
