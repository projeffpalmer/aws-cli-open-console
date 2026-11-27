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
from awscli.customizations.openconsole import docs
from awscli.testutils import mock, unittest

TOPIC = 'https://docs.aws.amazon.com/cli/latest/topic/'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'


def session_with_operations(*names):
    model = mock.Mock()
    model.operation_names = []
    for name in names:
        parts = [part.capitalize() for part in name.split('-')]
        model.operation_names.append(''.join(parts))
    session = mock.Mock()
    session.get_service_model.return_value = model
    session.get_available_services.return_value = ['ec2', 'sqs', 's3']
    return session


class TestDocsUrl(unittest.TestCase):
    def test_docs_home(self):
        self.assertEqual(docs.DOCS_HOME, 'https://docs.aws.amazon.com/')

    def test_aws_help(self):
        self.assertEqual(docs.docs_url('help', []), docs.DOCS_HOME)
        self.assertEqual(docs.docs_url('help', None), docs.DOCS_HOME)

    def test_topic(self):
        self.assertEqual(
            docs.docs_url('help', ['s3-config']), TOPIC + 's3-config.html'
        )

    def test_topics_index(self):
        self.assertEqual(
            docs.docs_url('help', ['topics']), TOPIC + 'index.html'
        )

    def test_topic_is_path_encoded(self):
        self.assertEqual(
            docs.docs_url('help', ['a/b c']), TOPIC + 'a%2Fb%20c.html'
        )

    def test_extra_help_tokens_use_the_home_page(self):
        self.assertEqual(docs.docs_url('help', ['a', 'b']), docs.DOCS_HOME)

    def test_service(self):
        self.assertEqual(
            docs.docs_url('ec2', ['help'], session_with_operations()),
            'https://docs.aws.amazon.com/ec2/',
        )

    def test_service_without_a_known_landing_page_uses_the_reference(self):
        for service in ('logs', 'elbv2', 'stepfunctions', 'sts', 's3api'):
            with self.subTest(service=service):
                self.assertEqual(
                    docs.docs_url(
                        service, ['help'], session_with_operations()
                    ),
                    f'{REFERENCE}{service}/index.html',
                )

    def test_unknown_subcommand_without_a_landing_page(self):
        self.assertEqual(
            docs.docs_url(
                'logs',
                ['no-such-op', 'help'],
                session_with_operations('describe-log-groups'),
            ),
            REFERENCE + 'logs/index.html',
        )

    def test_s3_guide_without_a_session(self):
        self.assertEqual(
            docs.docs_url('s3', ['help']), 'https://docs.aws.amazon.com/s3/'
        )

    def test_operation(self):
        self.assertEqual(
            docs.docs_url(
                'ec2',
                ['describe-instances', 'help'],
                session_with_operations('describe-instances'),
            ),
            REFERENCE + 'ec2/describe-instances.html',
        )

    def test_waiter(self):
        self.assertEqual(
            docs.docs_url('ec2', ['wait', 'instance-running', 'help']),
            REFERENCE + 'ec2/wait/instance-running.html',
        )

    def test_group(self):
        self.assertEqual(
            docs.docs_url('ec2', ['wait', 'help']),
            REFERENCE + 'ec2/wait/index.html',
        )

    def test_help_topics_under_a_service_stays_on_the_service(self):
        self.assertEqual(
            docs.docs_url('sqs', ['help', 'topics']),
            'https://docs.aws.amazon.com/sqs/',
        )

    def test_unknown_subcommand_uses_the_service_guide(self):
        self.assertEqual(
            docs.docs_url(
                'sqs',
                ['no-such-op', 'help'],
                session_with_operations('receive-message'),
            ),
            'https://docs.aws.amazon.com/sqs/',
        )

    def test_s3_subcommand(self):
        self.assertEqual(
            docs.docs_url('s3', ['ls', 's3://bucket', 'help']),
            REFERENCE + 's3/ls.html',
        )

    def test_configure_uses_the_cli_reference(self):
        self.assertEqual(
            docs.docs_url('configure', ['help']),
            REFERENCE + 'configure/index.html',
        )
