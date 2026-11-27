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
from urllib.parse import parse_qs, urlsplit

from awscli.customizations.openconsole import signin
from awscli.testutils import BaseAWSCommandParamsTest, mock

PKG = 'awscli.customizations.openconsole'
ACCOUNT = '123456789012'
LOGIN_PREFIX = 'https://signin.aws.amazon.com/federation?Action=login&'
SIGNIN_TOKEN = 'AQoDYXdzEJr//signin+token/value=='
FEDERATION_RESPONSE = {
    'Credentials': {
        'AccessKeyId': 'ASIAFEDERATED0000001',
        'SecretAccessKey': 'federated-secret',
        'SessionToken': 'federated-token',
    },
    'FederatedUser': {
        'Arn': f'arn:aws:sts::{ACCOUNT}:federated-user/{signin.ISSUER}',
        'FederatedUserId': f'{ACCOUNT}:{signin.ISSUER}',
    },
}


class ConsoleCommandTest(BaseAWSCommandParamsTest):
    def setUp(self):
        super().setUp()
        # A display, so the browser is opened on Linux too.
        self.environ['DISPLAY'] = ':0'
        self.environ.pop('AWS_CLI_CONSOLE_OPEN', None)
        self._patch_browser()
        http_patcher = mock.patch(
            f'{PKG}.signin._http_get',
            return_value=(200, '{"SigninToken": "tok"}'),
        )
        self.http_get = http_patcher.start()
        self.addCleanup(http_patcher.stop)

    def _patch_browser(self):
        open_patcher = mock.patch('webbrowser.open_new_tab', return_value=True)
        self.open_browser = open_patcher.start()
        self.addCleanup(open_patcher.stop)

    def operation_names(self):
        return [model.name for model, _ in self.operations_called]

    def assert_signed_in(self, destination):
        self.open_browser.assert_called_once()
        url = self.open_browser.call_args[0][0]
        self.assertTrue(url.startswith(LOGIN_PREFIX), url)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['Destination'], [destination])
        return query
