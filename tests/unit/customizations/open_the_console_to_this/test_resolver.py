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
import copy

from awscli.customizations.open_the_console_to_this import args as args_mod
from awscli.customizations.open_the_console_to_this import params
from awscli.customizations.open_the_console_to_this.resolver import (
    Context,
    Decision,
    resolve,
)
from awscli.testutils import mock, unittest
from tests.unit.customizations.open_the_console_to_this.test_db import (
    make_fixture_db,
)

EC2 = 'https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2'
SQS = 'https://us-west-2.console.aws.amazon.com/sqs/v3/home?region=us-west-2'
S3_BUCKETS = 'https://{host}/s3/buckets'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'


def _node(path, kind, intent, url, positional=None):
    name = path.rsplit('.', 1)[-1]
    node = {
        'name': name,
        'path': path,
        'tier': path.count('.'),
        'kind': kind,
        'title': None,
        'intent': intent,
        'url': dict({'needs_account': False, 'verified': None}, **url),
        'docs': {'best': REFERENCE + 'x.html', 'source': 'pattern'},
    }
    if positional is not None:
        node['positional'] = positional
    return node


def make_resolver_db():
    """The shared fixture plus nodes for variants, accounts and errors."""
    data = make_fixture_db()
    children = data['root']['children']
    sqs = children['sqs']['children']
    sqs['get-queue-attributes']['intent']['params'] = {
        'queue': {'arg': '--queue-url', 'parse': 'queue_url_name'},
        # A curated param may not replace a built-in name.
        'region': {'arg': '--queue-url', 'parse': 'first'},
    }
    sqs['get-queue-attributes']['url']['variants'] = [
        {
            'when': ['queue'],
            'template': (
                'https://{region}.{host}/sqs/v3/home?region={region}'
                '#/queues/{queue}'
            ),
        }
    ]
    s3 = {
        'name': 's3',
        'path': 'aws.s3',
        'tier': 1,
        'kind': 'custom',
        'title': None,
        'url': {
            'best': 'https://{host}/s3/home',
            'needs_account': False,
            'source': 'resolver:service',
        },
        'docs': {'best': REFERENCE + 's3/index.html', 'source': 'pattern'},
        'children': {},
    }
    s3['children']['ls'] = _node(
        'aws.s3.ls',
        'subcommand',
        {
            'verb': 'list',
            'resource_type': 'AWS::S3::Bucket',
            'id_args': [],
            'params': {
                'bucket': {'arg': 'paths', 'parse': 's3uri_bucket'},
                'prefix': {'arg': 'paths', 'parse': 's3uri_prefix'},
            },
        },
        {
            'best': S3_BUCKETS + '?region={region}',
            'variants': [
                {
                    'when': ['bucket', 'prefix'],
                    'template': (
                        S3_BUCKETS + '/{bucket}?region={region}'
                        '&prefix={prefix:query}&showversions=false'
                    ),
                },
                {
                    'when': ['bucket'],
                    'template': S3_BUCKETS + '/{bucket}?region={region}',
                },
            ],
            'source': 'curated',
        },
        positional=['paths'],
    )
    s3['children']['cp'] = _node(
        'aws.s3.cp',
        'subcommand',
        {
            'verb': 'view',
            'resource_type': None,
            'id_args': [],
            'params': {
                'bucket': {'arg': 'paths', 'parse': 's3_target_bucket'},
                'key': {'arg': 'paths', 'parse': 's3_target_key'},
            },
        },
        {
            'best': 'https://{host}/s3/home',
            'variants': [
                {
                    'when': ['bucket', 'key'],
                    'template': (
                        'https://{host}/s3/object/{bucket}?prefix={key:query}'
                    ),
                }
            ],
            'source': 'curated',
        },
        positional=['paths'],
    )
    children['s3'] = s3
    ecr = {
        'name': 'ecr',
        'path': 'aws.ecr',
        'tier': 1,
        'kind': 'service',
        'title': None,
        'console': {'slug': 'ecr', 'scope': 'regional', 'namespaces': []},
        'url': {
            'best': 'https://{region}.{host}/ecr/home?region={region}',
            'needs_account': False,
            'source': 'resolver:service',
        },
        'docs': {'best': REFERENCE + 'ecr/index.html', 'source': 'pattern'},
        'children': {},
    }
    ecr_repo = 'https://{region}.{host}/ecr/repositories'
    ecr['children']['describe-repositories'] = _node(
        'aws.ecr.describe-repositories',
        'operation',
        {
            'verb': 'list',
            'resource_type': 'AWS::ECR::Repository',
            'id_args': ['--repository-names'],
            'params': {},
        },
        {
            'best': ecr_repo + '?region={region}',
            'with_id': (ecr_repo + '/private/{account}/{id}?region={region}'),
            'with_ids': ecr_repo + '?region={region}&names={ids:query}',
            'needs_account': True,
            'source': 'resolver:list+view',
        },
    )
    ecr['children']['bad-encoding'] = _node(
        'aws.ecr.bad-encoding',
        'operation',
        {'verb': 'view', 'resource_type': None, 'id_args': ['--name']},
        {
            'best': ecr_repo + '?region={region}',
            'with_id': ecr_repo + '/{id:bogus}',
            'source': 'resolver:list+view',
        },
    )
    ecr['children']['needs-account-best'] = _node(
        'aws.ecr.needs-account-best',
        'operation',
        {'verb': 'list', 'resource_type': None, 'id_args': []},
        {
            'best': ecr_repo + '/private/{account}?region={region}',
            'needs_account': True,
            'source': 'resolver:list',
        },
    )
    ecr['children']['path-ids'] = _node(
        'aws.ecr.path-ids',
        'operation',
        {'verb': 'list', 'resource_type': None, 'id_args': ['--names']},
        {
            'best': ecr_repo + '?region={region}',
            'with_id': ecr_repo + '/{id}?region={region}',
            'with_ids': ecr_repo + '?region={region}#names={ids}',
            'source': 'resolver:list+view',
        },
    )
    ecr['children']['no-with-ids'] = _node(
        'aws.ecr.no-with-ids',
        'operation',
        {'verb': 'view', 'resource_type': None, 'id_args': ['--name']},
        {
            'best': ecr_repo + '?region={region}',
            'with_id': ecr_repo + '/{id}?region={region}',
            'source': 'resolver:list+view',
        },
    )
    ecr['children']['unknown-parse'] = _node(
        'aws.ecr.unknown-parse',
        'operation',
        {
            'verb': 'view',
            'resource_type': None,
            'id_args': [],
            'params': {'name': {'arg': '--name', 'parse': 'no_such_parse'}},
        },
        {
            'best': ecr_repo + '?region={region}',
            'variants': [{'when': ['name'], 'template': ecr_repo + '/{name}'}],
            'source': 'curated',
        },
    )
    children['ecr'] = ecr
    return data


class BaseResolverTest(unittest.TestCase):
    def setUp(self):
        self.root = make_resolver_db()['root']
        self.ctx = Context('us-west-2', 'aws')

    def resolve(self, argv, ctx=None):
        return resolve(self.root, argv[0], argv[1:], ctx or self.ctx)


class TestContextAndDecision(BaseResolverTest):
    def test_context_without_account_callable_returns_none(self):
        ctx = Context('us-east-1', 'aws')
        self.assertEqual(ctx.region, 'us-east-1')
        self.assertEqual(ctx.partition, 'aws')
        self.assertIsNone(ctx.account_id())

    def test_decision_has_the_six_fields(self):
        decision = self.resolve(['ec2'])
        self.assertIsInstance(decision, Decision)
        self.assertEqual(
            decision,
            Decision(
                url=EC2,
                node_path='aws.ec2',
                source='resolver:service',
                verb='home',
                params={},
                explanation='aws.ec2: used the url.best template.',
            ),
        )
        self.assertIn('aws.ec2', repr(decision))


class TestNodeLookup(BaseResolverTest):
    def test_service_home(self):
        decision = self.resolve(['sqs'])
        self.assertEqual(decision.url, SQS)
        self.assertEqual(decision.node_path, 'aws.sqs')
        self.assertEqual(decision.verb, 'home')

    def test_unknown_command_uses_the_console_resolver(self):
        decision = self.resolve(['no-such-service', 'list-things'])
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/go/view'
            '?service=no-such-service&region=us-west-2',
        )
        self.assertEqual(decision.source, 'resolver:fallback')
        self.assertEqual(decision.node_path, 'aws')
        self.assertEqual(decision.verb, 'home')

    def test_unknown_command_is_query_encoded(self):
        decision = self.resolve(['a b&c'])
        self.assertIn('service=a+b%26c&', decision.url)

    def test_unknown_command_in_another_partition(self):
        decision = self.resolve(
            ['nope'], Context('us-gov-west-1', 'aws-us-gov')
        )
        self.assertEqual(
            decision.url,
            'https://console.amazonaws-us-gov.com/go/view'
            '?service=nope&region=us-gov-west-1',
        )

    def test_unknown_subcommand_keeps_the_deepest_node(self):
        decision = self.resolve(['ec2', 'describe-nothing', '--x', 'y'])
        self.assertEqual(decision.url, EC2)
        self.assertEqual(decision.node_path, 'aws.ec2')

    def test_unknown_waiter_keeps_the_group(self):
        decision = self.resolve(['ec2', 'wait', 'nothing-ready'])
        self.assertEqual(decision.node_path, 'aws.ec2.wait')
        self.assertEqual(decision.url, EC2)

    def test_help_stops_the_walk(self):
        decision = self.resolve(['ec2', 'describe-instances', 'help'])
        self.assertEqual(decision.node_path, 'aws.ec2.describe-instances')
        self.assertEqual(decision.url, EC2 + '#Instances:')

    def test_partition_hosts(self):
        gov = self.resolve(['ec2'], Context('us-gov-west-1', 'aws-us-gov'))
        self.assertEqual(
            gov.url,
            'https://us-gov-west-1.console.amazonaws-us-gov.com/ec2/home'
            '?region=us-gov-west-1',
        )
        cn = self.resolve(['ec2'], Context('cn-north-1', 'aws-cn'))
        self.assertEqual(
            cn.url,
            'https://cn-north-1.console.amazonaws.cn/ec2/home'
            '?region=cn-north-1',
        )


class TestIdentifiers(BaseResolverTest):
    def test_no_id_gives_the_best_page(self):
        decision = self.resolve(['ec2', 'describe-instances'])
        self.assertEqual(decision.url, EC2 + '#Instances:')
        self.assertEqual(decision.verb, 'list')
        self.assertEqual(decision.params, {})
        self.assertEqual(decision.source, 'resolver:list+view')
        self.assertIn('url.best', decision.explanation)

    def test_one_id_gives_the_detail_page(self):
        decision = self.resolve(
            ['ec2', 'describe-instances', '--instance-ids', 'i-0abc']
        )
        self.assertEqual(
            decision.url, EC2 + '#InstanceDetails:instanceId=i-0abc'
        )
        self.assertEqual(decision.params, {'id': 'i-0abc'})
        self.assertIn('url.with_id', decision.explanation)

    def test_equals_form(self):
        decision = self.resolve(
            ['ec2', 'describe-instances', '--instance-ids=i-0abc']
        )
        self.assertEqual(
            decision.url, EC2 + '#InstanceDetails:instanceId=i-0abc'
        )

    def test_several_ids_give_the_filtered_list(self):
        decision = self.resolve(
            ['ec2', 'describe-instances', '--instance-ids', 'i-1', 'i-2']
        )
        self.assertEqual(decision.url, EC2 + '#Instances:instanceId=i-1,i-2')
        self.assertEqual(decision.params, {'id': 'i-1', 'ids': ['i-1', 'i-2']})
        self.assertIn('url.with_ids', decision.explanation)

    def test_waiter_uses_its_own_templates(self):
        decision = self.resolve(
            [
                'ec2',
                'wait',
                'instance-running',
                '--instance-ids',
                'i-1',
                '--dry-run',
            ]
        )
        self.assertEqual(decision.node_path, 'aws.ec2.wait.instance-running')
        self.assertEqual(decision.url, EC2 + '#InstanceDetails:instanceId=i-1')

    def test_flag_without_values_is_absent(self):
        decision = self.resolve(
            ['ec2', 'describe-instances', '--instance-ids']
        )
        self.assertEqual(decision.url, EC2 + '#Instances:')
        self.assertEqual(decision.params, {})

    def test_create_has_no_id(self):
        decision = self.resolve(['ec2', 'run-instances', '--count', '2'])
        self.assertEqual(decision.url, EC2 + '#LaunchInstances:')
        self.assertEqual(decision.verb, 'create')

    def test_variant_wins_over_with_id(self):
        url = 'https://sqs.us-west-2.amazonaws.com/111122223333/q'
        decision = self.resolve(
            ['sqs', 'get-queue-attributes', '--queue-url', url]
        )
        self.assertEqual(decision.url, SQS + '#/queues/q')
        self.assertEqual(decision.params, {'id': url, 'queue': 'q'})
        self.assertIn('url.variants[0]', decision.explanation)

    def test_id_is_path_encoded_by_default(self):
        # No path segment, so ``queue`` is absent and with_id is used.
        url = 'https://sqs.example.com'
        decision = self.resolve(
            ['sqs', 'get-queue-attributes', '--queue-url', url]
        )
        self.assertEqual(
            decision.url, SQS + '#/queues/https%3A%2F%2Fsqs.example.com'
        )
        self.assertIn('url.with_id', decision.explanation)

    def test_ids_are_encoded_one_by_one(self):
        decision = self.resolve(['ecr', 'path-ids', '--names', 'a/b', 'c d'])
        self.assertEqual(
            decision.url,
            'https://us-west-2.console.aws.amazon.com/ecr/repositories'
            '?region=us-west-2#names=a%2Fb,c%20d',
        )

    def test_ids_query_encoding(self):
        decision = self.resolve(
            [
                'ecr',
                'describe-repositories',
                '--repository-names',
                'a/b',
                'c d',
            ]
        )
        self.assertTrue(
            decision.url.endswith('&names=a%2Fb,c+d'), decision.url
        )

    def test_several_ids_without_with_ids_give_the_list_page(self):
        decision = self.resolve(['ecr', 'no-with-ids', '--name', 'a', 'b'])
        self.assertEqual(
            decision.url,
            'https://us-west-2.console.aws.amazon.com/ecr/repositories'
            '?region=us-west-2',
        )
        self.assertEqual(decision.params, {'id': 'a', 'ids': ['a', 'b']})
        self.assertIn('url.best', decision.explanation)

    def test_id_count_picks_the_template(self):
        repos = 'https://us-west-2.console.aws.amazon.com/ecr/repositories'
        cases = [
            # Two ids, no with_ids: the plain list page.
            (['no-with-ids', '--name', 'a', 'b'], 'url.best'),
            # Two ids, with_ids present: the filtered list page.
            (['path-ids', '--names', 'a', 'b'], 'url.with_ids'),
            # One id: the detail page, with or without with_ids.
            (['no-with-ids', '--name', 'a'], 'url.with_id'),
            (['path-ids', '--names', 'a'], 'url.with_id'),
        ]
        expected_urls = {
            'url.best': repos + '?region=us-west-2',
            'url.with_ids': repos + '?region=us-west-2#names=a,b',
            'url.with_id': repos + '/a?region=us-west-2',
        }
        for argv, template in cases:
            with self.subTest(argv=argv):
                decision = self.resolve(['ecr'] + argv)
                self.assertEqual(decision.url, expected_urls[template])
                self.assertEqual(
                    decision.explanation,
                    f'{decision.node_path}: used the {template} template.',
                )


class TestVariants(BaseResolverTest):
    BUCKETS = 'https://console.aws.amazon.com/s3/buckets'

    def test_no_path_gives_the_best_page(self):
        decision = self.resolve(['s3', 'ls'])
        self.assertEqual(decision.url, self.BUCKETS + '?region=us-west-2')
        self.assertEqual(decision.source, 'curated')

    def test_bucket_variant(self):
        decision = self.resolve(['s3', 'ls', 's3://photos'])
        self.assertEqual(
            decision.url, self.BUCKETS + '/photos?region=us-west-2'
        )
        self.assertEqual(decision.params, {'bucket': 'photos'})
        self.assertIn('url.variants[1]', decision.explanation)

    def test_bucket_and_prefix_variant(self):
        decision = self.resolve(
            ['s3', 'ls', 's3://photos/2026/', '--recursive']
        )
        self.assertEqual(
            decision.url,
            self.BUCKETS + '/photos?region=us-west-2&prefix=2026%2F'
            '&showversions=false',
        )
        self.assertEqual(
            decision.params, {'bucket': 'photos', 'prefix': '2026/'}
        )
        self.assertIn('url.variants[0]', decision.explanation)

    def test_bucket_without_scheme(self):
        decision = self.resolve(['s3', 'ls', 'photos/a/b'])
        self.assertEqual(decision.params, {'bucket': 'photos', 'prefix': 'a/'})

    def test_target_of_a_copy(self):
        decision = self.resolve(['s3', 'cp', 'local.txt', 's3://b/k/x.txt'])
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/s3/object/b?prefix=k%2Fx.txt',
        )

    def test_source_of_a_download(self):
        decision = self.resolve(['s3', 'cp', 's3://b/k.txt', 'local.txt'])
        self.assertEqual(decision.params, {'bucket': 'b', 'key': 'k.txt'})

    def test_curated_param_cannot_replace_region(self):
        decision = self.resolve(
            ['sqs', 'get-queue-attributes', '--queue-url', 'https://x/1/q']
        )
        self.assertNotIn('region', decision.params)
        self.assertIn('region=us-west-2', decision.url)

    def test_unknown_parse_function_means_absent(self):
        decision = self.resolve(['ecr', 'unknown-parse', '--name', 'r'])
        self.assertEqual(decision.params, {})
        self.assertIn('url.best', decision.explanation)


class TestAccount(BaseResolverTest):
    REPOS = 'https://us-west-2.console.aws.amazon.com/ecr/repositories'

    def test_account_is_used_when_the_template_needs_it(self):
        account = mock.Mock(return_value='111122223333')
        decision = self.resolve(
            ['ecr', 'describe-repositories', '--repository-names', 'r'],
            Context('us-west-2', 'aws', account),
        )
        self.assertEqual(
            decision.url,
            self.REPOS + '/private/111122223333/r?region=us-west-2',
        )
        account.assert_called_once_with()
        self.assertNotIn('account', decision.params)

    def test_account_is_not_looked_up_when_not_needed(self):
        account = mock.Mock(return_value='111122223333')
        self.resolve(
            ['ecr', 'describe-repositories'],
            Context('us-west-2', 'aws', account),
        )
        self.resolve(
            ['ec2', 'describe-instances', '--instance-ids', 'i-1'],
            Context('us-west-2', 'aws', account),
        )
        account.assert_not_called()

    def test_missing_account_falls_down_the_chain(self):
        account = mock.Mock(return_value=None)
        decision = self.resolve(
            ['ecr', 'describe-repositories', '--repository-names', 'r'],
            Context('us-west-2', 'aws', account),
        )
        self.assertEqual(decision.url, self.REPOS + '?region=us-west-2')
        account.assert_called_once_with()

    def test_failing_account_lookup_counts_as_missing(self):
        account = mock.Mock(side_effect=RuntimeError('boom'))
        decision = self.resolve(
            ['ecr', 'describe-repositories', '--repository-names', 'r'],
            Context('us-west-2', 'aws', account),
        )
        self.assertEqual(decision.url, self.REPOS + '?region=us-west-2')

    def test_account_is_looked_up_once(self):
        account = mock.Mock(return_value=None)
        decision = self.resolve(
            ['ecr', 'needs-account-best'],
            Context('us-west-2', 'aws', account),
        )
        account.assert_called_once_with()
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/console/home?region=us-west-2',
        )
        self.assertEqual(decision.source, 'resolver:fallback')
        self.assertEqual(decision.node_path, 'aws.ecr.needs-account-best')


class TestNeverRaises(BaseResolverTest):
    def test_bad_encoding_falls_back_to_best(self):
        decision = self.resolve(['ecr', 'bad-encoding', '--name', 'r'])
        self.assertEqual(decision.url, self.REPOS_BEST)
        self.assertEqual(decision.node_path, 'aws.ecr.bad-encoding')
        self.assertIn('unexpected error', decision.explanation)

    REPOS_BEST = (
        'https://us-west-2.console.aws.amazon.com/ecr/repositories'
        '?region=us-west-2'
    )

    def test_broken_root_gives_the_console_home(self):
        decision = resolve(None, 'ec2', [], self.ctx)
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/console/home?region=us-west-2',
        )
        self.assertEqual(decision.source, 'resolver:fallback')

    def test_node_without_url_gives_the_console_home(self):
        root = copy.deepcopy(self.root)
        del root['children']['ec2']['url']
        decision = resolve(root, 'ec2', [], self.ctx)
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/console/home?region=us-west-2',
        )

    def test_odd_tokens(self):
        for remaining in (['--'], ['-', '--x='], ['--', 'help'], ['\x00']):
            decision = self.resolve(['ec2', 'describe-instances'] + remaining)
            self.assertTrue(decision.url.startswith('https://'), remaining)


class TestFlagsAndScalars(BaseResolverTest):
    BUCKETS = 'https://console.aws.amazon.com/s3/buckets'
    FN = 'https://us-west-2.console.aws.amazon.com/lambda/home'

    def setUp(self):
        super().setUp()
        children = self.root['children']
        self.ls = children['s3']['children']['ls']
        lam = _node(
            'aws.lambda',
            'service',
            None,
            {
                'best': self.FN + '?region={region}',
                'source': 'resolver:service',
            },
        )
        lam['children'] = {
            'invoke': _node(
                'aws.lambda.invoke',
                'operation',
                {
                    'verb': 'view',
                    'resource_type': None,
                    'id_args': [],
                    'params': {'fn': {'arg': '--function-name'}},
                },
                {
                    'best': self.FN + '?region={region}#/functions',
                    'variants': [
                        {
                            'when': ['fn'],
                            'template': (
                                self.FN + '?region={region}#/functions/{fn}'
                            ),
                        }
                    ],
                    'source': 'curated',
                },
                positional=['outfile'],
            )
        }
        children['lambda'] = lam
        self.invoke = lam['children']['invoke']

    def test_flag_before_positional_with_flags_hint(self):
        self.ls['flags'] = ['recursive', 'human-readable']
        decision = self.resolve(['s3', 'ls', '--recursive', 's3://b/p/'])
        self.assertEqual(decision.params, {'bucket': 'b', 'prefix': 'p/'})
        self.assertEqual(
            decision.url,
            self.BUCKETS
            + '/b?region=us-west-2&prefix=p%2F&showversions=false',
        )

    def test_flag_before_positional_without_hint_is_greedy(self):
        decision = self.resolve(['s3', 'ls', '--recursive', 's3://b/p/'])
        self.assertEqual(decision.params, {})
        self.assertEqual(decision.url, self.BUCKETS + '?region=us-west-2')

    def test_scalar_hint_leaves_the_positional_alone(self):
        self.invoke['scalars'] = ['function-name']
        decision = self.resolve(
            ['lambda', 'invoke', '--function-name', 'f', 'out.json']
        )
        self.assertEqual(decision.params, {'fn': 'f'})
        self.assertEqual(
            decision.url, self.FN + '?region=us-west-2#/functions/f'
        )

    def test_without_scalar_hint_the_positional_joins_the_values(self):
        # ``first`` still picks ``f``; the positional is swallowed.
        decision = self.resolve(
            ['lambda', 'invoke', '--function-name', 'f', 'out.json']
        )
        self.assertEqual(decision.params, {'fn': 'f'})

    def test_hints_reach_the_tokenizer(self):
        self.ls['flags'] = ['recursive']
        self.ls['scalars'] = ['page-size']
        with mock.patch(
            'awscli.customizations.open_the_console_to_this.args'
            '.parse_remaining',
            wraps=args_mod.parse_remaining,
        ) as parse:
            self.resolve(['s3', 'ls', 's3://b/'])
        parse.assert_called_once_with(
            ['s3://b/'],
            ['paths'],
            flags=['recursive'],
            scalars=['page-size'],
        )

    def test_null_hints_are_accepted(self):
        self.ls['flags'] = None
        self.ls['scalars'] = None
        decision = self.resolve(['s3', 'ls', 's3://b/p/'])
        self.assertEqual(decision.params, {'bucket': 'b', 'prefix': 'p/'})


class TestBareFlagParams(BaseResolverTest):
    BUCKETS = 'https://console.aws.amazon.com/s3/buckets'

    def setUp(self):
        super().setUp()
        self.ls = self.root['children']['s3']['children']['ls']
        self.ls['flags'] = ['recursive']
        self.ls['intent']['params']['recursive'] = {
            'arg': '--recursive',
            'parse': 'present',
        }
        self.ls['intent']['params']['size'] = {'arg': '--page-size'}
        self.ls['url']['variants'].insert(
            0,
            {
                'when': ['bucket', 'recursive'],
                'template': self.BUCKETS + '/{bucket}?region={region}&r=1',
            },
        )

    def test_present_sees_a_bare_flag(self):
        decision = self.resolve(['s3', 'ls', 's3://b', '--recursive'])
        self.assertEqual(decision.params, {'bucket': 'b', 'recursive': '1'})
        self.assertEqual(
            decision.url, self.BUCKETS + '/b?region=us-west-2&r=1'
        )
        self.assertIn('url.variants[0]', decision.explanation)

    def test_present_is_absent_when_not_typed(self):
        decision = self.resolve(['s3', 'ls', 's3://b'])
        self.assertEqual(decision.params, {'bucket': 'b'})
        self.assertEqual(decision.url, self.BUCKETS + '/b?region=us-west-2')

    def test_other_parse_functions_ignore_a_bare_flag(self):
        decision = self.resolve(['s3', 'ls', 's3://b', '--page-size'])
        self.assertEqual(decision.params, {'bucket': 'b'})

    def test_parse_function_is_called_with_the_empty_list(self):
        with mock.patch.object(
            params, 'parse_param', wraps=params.parse_param
        ) as parse:
            self.resolve(['s3', 'ls', '--recursive'])
        self.assertIn(mock.call('present', []), parse.call_args_list)


class TestSeveralIdsNeverOpenTheFirstId(BaseResolverTest):
    REPOS = 'https://us-west-2.console.aws.amazon.com/ecr/repositories'

    def test_with_ids_missing_account_falls_to_best(self):
        node = self.root['children']['ecr']['children']['path-ids']
        node['url']['with_ids'] = (
            'https://{region}.{host}/ecr/private/{account}?names={ids}'
        )
        account = mock.Mock(return_value=None)
        decision = self.resolve(
            ['ecr', 'path-ids', '--names', 'a', 'b'],
            Context('us-west-2', 'aws', account),
        )
        self.assertEqual(decision.url, self.REPOS + '?region=us-west-2')
        self.assertIn('url.best', decision.explanation)
        account.assert_called_once_with()

    def test_with_ids_missing_param_falls_to_best(self):
        node = self.root['children']['ecr']['children']['path-ids']
        node['url']['with_ids'] = (
            'https://{region}.{host}/ecr/{nope}?names={ids}'
        )
        decision = self.resolve(['ecr', 'path-ids', '--names', 'a', 'b'])
        self.assertEqual(decision.url, self.REPOS + '?region=us-west-2')
        self.assertEqual(decision.params, {'id': 'a', 'ids': ['a', 'b']})
        self.assertIn('url.best', decision.explanation)

    def test_one_id_still_uses_with_id(self):
        node = self.root['children']['ecr']['children']['path-ids']
        node['url']['with_ids'] = (
            'https://{region}.{host}/ecr/{nope}?names={ids}'
        )
        decision = self.resolve(['ecr', 'path-ids', '--names', 'a'])
        self.assertEqual(decision.url, self.REPOS + '/a?region=us-west-2')


class TestParseFunctions(unittest.TestCase):
    def check(self, name, values, expected):
        self.assertEqual(
            params.parse_param(name, values), expected, (name, values)
        )

    def test_every_contract_function_exists(self):
        self.assertEqual(
            sorted(params.PARSERS),
            sorted(
                [
                    'first',
                    'last',
                    's3uri_bucket',
                    's3uri_key',
                    's3uri_prefix',
                    's3uri_object',
                    's3_target_bucket',
                    's3_target_key',
                    's3_target_prefix',
                    'arn_resource',
                    'arn_account',
                    'arn_region',
                    'queue_url_name',
                    'queue_url_account',
                    'basename',
                    'present',
                    'is_arn',
                    'arn_type',
                    'arn_name',
                    'before_colon',
                    'after_colon',
                    'before_dot',
                    'first_label',
                    'lower',
                    'strip_leading_slash',
                    'ensure_trailing_slash',
                    'strip_wildcard_suffix',
                    'secret_name',
                    's3uri_dir',
                    'prefix_dir',
                    's3_target_object',
                    'filters_first_value',
                ]
            ),
        )

    def test_default_is_first(self):
        self.check(None, ['a', 'b'], 'a')
        self.check(None, [], None)

    def test_first_and_last(self):
        self.check('first', ['a', 'b'], 'a')
        self.check('last', ['a', 'b'], 'b')
        self.check('last', [], None)

    def test_unknown_name_raises_key_error(self):
        with self.assertRaises(KeyError):
            params.parse_param('nope', ['a'])

    def test_s3uri_bucket(self):
        self.check('s3uri_bucket', ['s3://b/k'], 'b')
        self.check('s3uri_bucket', ['b/k'], 'b')
        self.check('s3uri_bucket', ['b'], 'b')
        self.check('s3uri_bucket', ['local', 's3://b2/x'], 'b2')
        self.check('s3uri_bucket', ['s3://'], None)
        self.check('s3uri_bucket', [], None)

    def test_s3uri_key(self):
        self.check('s3uri_key', ['s3://b/a/b.txt'], 'a/b.txt')
        self.check('s3uri_key', ['s3://b/'], None)
        self.check('s3uri_key', ['s3://b'], None)

    def test_s3uri_prefix(self):
        self.check('s3uri_prefix', ['s3://b/a/b/c.txt'], 'a/b/')
        self.check('s3uri_prefix', ['s3://b/a/'], 'a/')
        self.check('s3uri_prefix', ['s3://b/c.txt'], None)
        self.check('s3uri_prefix', ['b'], None)

    def test_s3uri_object(self):
        self.check('s3uri_object', ['s3://b/a/c.txt'], 'a/c.txt')
        self.check('s3uri_object', ['s3://b/a/'], None)
        self.check('s3uri_object', ['s3://b'], None)

    def test_s3_target(self):
        upload = ['f.txt', 's3://b/k/f.txt']
        download = ['s3://src/k/f.txt', 'f.txt']
        both = ['s3://src/a.txt', 's3://dst/d/']
        self.check('s3_target_bucket', upload, 'b')
        self.check('s3_target_key', upload, 'k/f.txt')
        self.check('s3_target_prefix', upload, 'k/')
        self.check('s3_target_bucket', download, 'src')
        self.check('s3_target_key', download, 'k/f.txt')
        self.check('s3_target_bucket', both, 'dst')
        self.check('s3_target_key', both, 'd/')
        self.check('s3_target_prefix', both, 'd/')
        self.check('s3_target_bucket', [], None)

    def test_arn_functions(self):
        role = 'arn:aws:iam::111122223333:role/path/my-role'
        fn = 'arn:aws:lambda:us-west-2:111122223333:function:my-fn:prod'
        topic = 'arn:aws:sns:us-west-2:111122223333:my-topic'
        self.check('arn_resource', [role], 'path/my-role')
        self.check('arn_resource', [fn], 'my-fn:prod')
        self.check('arn_resource', [topic], 'my-topic')
        self.check('arn_account', [role], '111122223333')
        self.check('arn_region', [role], None)
        self.check('arn_region', [fn], 'us-west-2')
        self.check('arn_resource', ['not-an-arn'], None)
        self.check('arn_account', ['arn:aws:s3'], None)

    def test_queue_url_functions(self):
        url = 'https://sqs.us-west-2.amazonaws.com/111122223333/my-queue'
        self.check('queue_url_name', [url], 'my-queue')
        self.check('queue_url_account', [url], '111122223333')
        self.check('queue_url_name', ['https://sqs.example.com'], None)
        self.check('queue_url_account', ['https://h/only'], None)

    def test_basename(self):
        self.check('basename', ['a/b/c'], 'c')
        self.check('basename', ['c'], 'c')
        self.check('basename', ['a/b/'], None)
