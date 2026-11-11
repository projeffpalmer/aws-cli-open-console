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
import pytest

from awscli.customizations.open_the_console_to_this import (
    db,
    follow,
    resolver,
)

REGION = 'us-west-2'
EC2 = f'https://{REGION}.console.aws.amazon.com/ec2/home?region={REGION}'


@pytest.fixture(scope='module')
def root():
    return db.load_db()['root']


def resolve(root, argv, response):
    ctx = resolver.Context(REGION, 'aws')
    return follow.resolve_after_run(root, argv[0], argv[1:], response, ctx)


class TestFindValues:
    def test_matches_ignoring_case_and_dashes(self):
        response = {'DBInstance': {'DBInstanceIdentifier': 'db1'}}
        assert follow.find_values(response, 'db-instance-identifier') == [
            'db1'
        ]

    def test_plural_option_matches_singular_key_across_lists(self):
        response = {
            'Instances': [{'InstanceId': 'i-1'}, {'InstanceId': 'i-2'}]
        }
        assert follow.find_values(response, 'instance-ids') == ['i-1', 'i-2']

    def test_exact_key_wins_over_singular(self):
        response = {'InstanceIds': ['i-1'], 'InstanceId': 'i-9'}
        assert follow.find_values(response, 'instance-ids') == ['i-1']

    def test_shallowest_match_wins(self):
        response = {
            'Table': {'Name': 'outer', 'Index': {'Name': 'inner'}},
        }
        assert follow.find_values(response, 'name') == ['outer']

    def test_repeats_are_dropped_in_order(self):
        pages = [
            {'Items': [{'Id': 'a'}, {'Id': 'b'}]},
            {'Items': [{'Id': 'a'}]},
        ]
        assert follow.find_values(pages, 'id') == ['a', 'b']

    def test_response_metadata_and_non_strings_are_ignored(self):
        response = {
            'ResponseMetadata': {'RequestId': 'r'},
            'Count': {'RequestId': 3},
        }
        assert follow.find_values(response, 'request-id') == []

    def test_none_response(self):
        assert follow.find_values(None, 'table-name') == []


class TestResolveAfterRun:
    def test_create_table_opens_the_table(self, root):
        decision = resolve(
            root,
            ['dynamodb', 'create-table', '--table-name', 'MusicCollection'],
            {'TableDescription': {'TableName': 'MusicCollection'}},
        )
        assert decision.url == (
            f'https://{REGION}.console.aws.amazon.com/dynamodbv2/home'
            f'?region={REGION}#table?name=MusicCollection'
        )
        assert decision.node_path == 'aws.dynamodb.describe-table'

    def test_run_instances_opens_the_instance(self, root):
        decision = resolve(
            root,
            ['ec2', 'run-instances', '--image-id', 'ami-1'],
            {'Instances': [{'InstanceId': 'i-0aaa'}]},
        )
        assert decision.url == EC2 + '#InstanceDetails:instanceId=i-0aaa'

    def test_typed_value_when_the_response_has_none(self, root):
        decision = resolve(
            root,
            ['s3api', 'create-bucket', '--bucket', 'photos'],
            {'Location': '/photos'},
        )
        assert decision.url == (
            f'https://console.aws.amazon.com/s3/buckets/photos?region={REGION}'
        )

    def test_typed_positionals_reach_a_sibling(self, root):
        decision = resolve(root, ['s3', 'mb', 's3://photos'], None)
        assert decision.url == (
            f'https://console.aws.amazon.com/s3/buckets/photos?region={REGION}'
        )

    def test_create_without_an_identifier_opens_the_list(self, root):
        decision = resolve(root, ['dynamodb', 'create-table'], {})
        assert decision.url == (
            f'https://{REGION}.console.aws.amazon.com/dynamodbv2/home'
            f'?region={REGION}#table'
        )

    def test_no_resource_falls_back_to_the_typed_command(self, root):
        ctx = resolver.Context(REGION, 'aws')
        assert resolve(root, ['configure', 'list'], None) == resolver.resolve(
            root, 'configure', ['list'], ctx
        )

    def test_unknown_command_falls_back(self, root):
        decision = resolve(root, ['not-a-service', 'x'], {'Name': 'n'})
        assert decision.source == resolver.FALLBACK_SOURCE


class TestViewCandidates:
    def test_canonical_describe_comes_first(self, root):
        dynamodb = root['children']['dynamodb']
        node = dynamodb['children']['create-table']
        names = [c['name'] for c in follow.view_candidates(node, dynamodb)]
        assert names[0] == 'describe-table'

    def test_the_node_itself_comes_first_when_it_shows_one(self, root):
        ec2 = root['children']['ec2']
        node = ec2['children']['describe-instances']
        assert follow.view_candidates(node, ec2)[0] is node
