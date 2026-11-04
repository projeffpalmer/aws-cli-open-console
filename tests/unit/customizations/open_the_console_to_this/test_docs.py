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
from awscli.customizations.open_the_console_to_this import db, docs
from awscli.testutils import unittest
from tests.unit.customizations.open_the_console_to_this.test_db import (
    make_fixture_db,
)

TOPIC = 'https://docs.aws.amazon.com/cli/latest/topic/'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'


class TestDocsUrl(unittest.TestCase):
    def setUp(self):
        self.root = make_fixture_db()['root']

    def url_for(self, tokens):
        node, _, rest = db.find_node(self.root, tokens)
        return docs.docs_url(self.root, node, rest)

    def test_docs_home(self):
        self.assertEqual(docs.DOCS_HOME, 'https://docs.aws.amazon.com/')

    def test_aws_help(self):
        self.assertEqual(self.url_for(['help']), docs.DOCS_HOME)

    def test_root_without_tokens(self):
        self.assertEqual(
            docs.docs_url(self.root, self.root, []), docs.DOCS_HOME
        )
        self.assertEqual(
            docs.docs_url(self.root, self.root, None), docs.DOCS_HOME
        )

    def test_topic(self):
        self.assertEqual(
            self.url_for(['help', 's3-config']), TOPIC + 's3-config.html'
        )

    def test_topics_index(self):
        self.assertEqual(
            self.url_for(['help', 'topics']), TOPIC + 'index.html'
        )

    def test_topic_is_path_encoded(self):
        self.assertEqual(
            self.url_for(['help', 'a/b c']), TOPIC + 'a%2Fb%20c.html'
        )

    def test_root_with_other_tokens_uses_root_docs(self):
        self.root['docs']['best'] = 'https://example.invalid/root'
        self.assertEqual(
            self.url_for(['nope', 'help']), 'https://example.invalid/root'
        )
        self.assertEqual(
            self.url_for(['help', 'a', 'b']), 'https://example.invalid/root'
        )

    def test_service(self):
        self.assertEqual(
            self.url_for(['ec2', 'help']), 'https://docs.aws.amazon.com/ec2/'
        )

    def test_operation(self):
        self.assertEqual(
            self.url_for(['ec2', 'describe-instances', 'help']),
            REFERENCE + 'ec2/describe-instances.html',
        )

    def test_waiter(self):
        self.assertEqual(
            self.url_for(['ec2', 'wait', 'instance-running', 'help']),
            REFERENCE + 'ec2/wait/instance-running.html',
        )

    def test_group(self):
        self.assertEqual(
            self.url_for(['ec2', 'wait', 'help']),
            REFERENCE + 'ec2/wait/index.html',
        )

    def test_non_root_ignores_topic_shape(self):
        self.assertEqual(
            self.url_for(['sqs', 'help', 'topics']),
            'https://docs.aws.amazon.com/sqs/',
        )

    def test_deepest_matched_node_for_unknown_subcommand(self):
        self.assertEqual(
            self.url_for(['sqs', 'no-such-op', 'help']),
            'https://docs.aws.amazon.com/sqs/',
        )
