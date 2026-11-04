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
import json
import os
import shutil
import tempfile

from awscli.customizations.open_the_console_to_this import db
from awscli.testutils import mock, unittest

ORIGINAL_DB_PATH = db.DB_PATH
REGIONAL = 'https://{region}.{host}'
EC2_HOME = REGIONAL + '/ec2/home?region={region}'
SQS_HOME = REGIONAL + '/sqs/v3/home?region={region}'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'
_EC2_INSTANCE_INTENT = {
    'verb': 'list',
    'resource_type': 'AWS::EC2::Instance',
    'id_args': ['--instance-ids'],
    'params': {},
}
_EC2_INSTANCE_URL = {
    'best': EC2_HOME + '#Instances:',
    'with_id': EC2_HOME + '#InstanceDetails:instanceId={id:raw}',
    'with_ids': EC2_HOME + '#Instances:instanceId={ids:raw}',
    'needs_account': False,
    'source': 'resolver:list+view',
    'verified': '2026-11-04',
    'note': None,
}

# A small database in the shape of contract section 1: root, two
# services, a few operations and one wait group with one waiter.
FIXTURE_DB = {
    'schema': 1,
    'generated': {
        'awscli': '2.39.3',
        'snapshot': '2026-11-04',
        'resource_types': 2,
    },
    'root': {
        'name': 'aws',
        'path': 'aws',
        'tier': 0,
        'kind': 'root',
        'title': None,
        'url': {
            'best': 'https://{host}/console/home?region={region}',
            'source': 'curated',
            'verified': '2026-11-04',
        },
        'docs': {
            'best': 'https://docs.aws.amazon.com/',
            'source': 'curated',
            'fallback': None,
        },
        'children': {
            'ec2': {
                'name': 'ec2',
                'path': 'aws.ec2',
                'tier': 1,
                'kind': 'service',
                'title': 'Amazon Elastic Compute Cloud',
                'console': {
                    'slug': 'ec2',
                    'scope': 'regional',
                    'namespaces': ['EC2'],
                },
                'url': {
                    'best': EC2_HOME,
                    'needs_account': False,
                    'source': 'resolver:service',
                    'verified': '2026-11-04',
                },
                'docs': {
                    'best': 'https://docs.aws.amazon.com/ec2/',
                    'source': 'probe',
                    'fallback': REFERENCE + 'ec2/index.html',
                },
                'children': {
                    'describe-instances': {
                        'name': 'describe-instances',
                        'path': 'aws.ec2.describe-instances',
                        'tier': 2,
                        'kind': 'operation',
                        'title': None,
                        'intent': copy.deepcopy(_EC2_INSTANCE_INTENT),
                        'url': copy.deepcopy(_EC2_INSTANCE_URL),
                        'docs': {
                            'best': REFERENCE + 'ec2/describe-instances.html',
                            'source': 'pattern',
                            'fallback': None,
                        },
                    },
                    'run-instances': {
                        'name': 'run-instances',
                        'path': 'aws.ec2.run-instances',
                        'tier': 2,
                        'kind': 'operation',
                        'title': None,
                        'intent': {
                            'verb': 'create',
                            'resource_type': 'AWS::EC2::Instance',
                            'id_args': [],
                            'params': {},
                        },
                        'url': {
                            'best': EC2_HOME + '#LaunchInstances:',
                            'needs_account': False,
                            'source': 'resolver:create',
                            'verified': '2026-11-04',
                        },
                        'docs': {
                            'best': REFERENCE + 'ec2/run-instances.html',
                            'source': 'pattern',
                            'fallback': None,
                        },
                    },
                    'wait': {
                        'name': 'wait',
                        'path': 'aws.ec2.wait',
                        'tier': 2,
                        'kind': 'group',
                        'title': None,
                        'url': {
                            'best': EC2_HOME,
                            'needs_account': False,
                            'source': 'service-home',
                            'verified': '2026-11-04',
                        },
                        'docs': {
                            'best': REFERENCE + 'ec2/wait/index.html',
                            'source': 'pattern',
                            'fallback': None,
                        },
                        'children': {
                            'instance-running': {
                                'name': 'instance-running',
                                'path': 'aws.ec2.wait.instance-running',
                                'tier': 3,
                                'kind': 'waiter',
                                'title': None,
                                'intent': copy.deepcopy(_EC2_INSTANCE_INTENT),
                                'url': copy.deepcopy(_EC2_INSTANCE_URL),
                                'docs': {
                                    'best': (
                                        REFERENCE
                                        + 'ec2/wait/instance-running.html'
                                    ),
                                    'source': 'pattern',
                                    'fallback': None,
                                },
                            },
                        },
                    },
                },
            },
            'sqs': {
                'name': 'sqs',
                'path': 'aws.sqs',
                'tier': 1,
                'kind': 'service',
                'title': 'Amazon Simple Queue Service',
                'console': {
                    'slug': 'sqs',
                    'scope': 'regional',
                    'namespaces': ['SQS'],
                },
                'url': {
                    'best': SQS_HOME,
                    'needs_account': False,
                    'source': 'resolver:service',
                    'verified': '2026-11-04',
                },
                'docs': {
                    'best': 'https://docs.aws.amazon.com/sqs/',
                    'source': 'probe',
                    'fallback': REFERENCE + 'sqs/index.html',
                },
                'children': {
                    'list-queues': {
                        'name': 'list-queues',
                        'path': 'aws.sqs.list-queues',
                        'tier': 2,
                        'kind': 'operation',
                        'title': None,
                        'intent': {
                            'verb': 'list',
                            'resource_type': 'AWS::SQS::Queue',
                            'id_args': [],
                            'params': {},
                        },
                        'url': {
                            'best': SQS_HOME + '#/queues',
                            'needs_account': False,
                            'source': 'resolver:list',
                            'verified': 'path-only',
                        },
                        'docs': {
                            'best': REFERENCE + 'sqs/list-queues.html',
                            'source': 'pattern',
                            'fallback': None,
                        },
                    },
                    'get-queue-attributes': {
                        'name': 'get-queue-attributes',
                        'path': 'aws.sqs.get-queue-attributes',
                        'tier': 2,
                        'kind': 'operation',
                        'title': None,
                        'intent': {
                            'verb': 'view',
                            'resource_type': 'AWS::SQS::Queue',
                            'id_args': ['--queue-url'],
                            'params': {},
                        },
                        'url': {
                            'best': SQS_HOME + '#/queues',
                            'with_id': SQS_HOME + '#/queues/{id}',
                            'needs_account': False,
                            'source': 'resolver:list+view',
                            'verified': 'path-only',
                        },
                        'docs': {
                            'best': (
                                REFERENCE + 'sqs/get-queue-attributes.html'
                            ),
                            'source': 'pattern',
                            'fallback': None,
                        },
                    },
                },
            },
        },
    },
}


def make_fixture_db():
    """Return a fresh deep copy of the fixture database."""
    return copy.deepcopy(FIXTURE_DB)


def write_fixture_db(directory, data=None):
    """Write ``data`` (default: the fixture) as compact JSON; return path."""
    if data is None:
        data = make_fixture_db()
    path = os.path.join(directory, 'commands.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), sort_keys=True)
    return path


class TestLoadDb(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.path = write_fixture_db(self.tempdir)
        db.reset_cache()
        patcher = mock.patch.object(db, 'DB_PATH', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(db.reset_cache)
        self.addCleanup(shutil.rmtree, self.tempdir)

    def test_default_path_points_into_awscli_data(self):
        expected = os.path.join(
            'awscli', 'data', 'open_the_console_to_this', 'commands.json'
        )
        self.assertTrue(ORIGINAL_DB_PATH.endswith(expected), ORIGINAL_DB_PATH)
        self.assertTrue(os.path.isabs(ORIGINAL_DB_PATH))

    def test_loads_the_file(self):
        data = db.load_db()
        self.assertEqual(data['schema'], 1)
        self.assertEqual(data['root']['path'], 'aws')
        self.assertEqual(data, FIXTURE_DB)

    def test_reads_the_file_once(self):
        first = db.load_db()
        with mock.patch('builtins.open') as mock_open:
            second = db.load_db()
        self.assertIs(first, second)
        mock_open.assert_not_called()

    def test_reset_cache_reloads(self):
        first = db.load_db()
        db.reset_cache()
        second = db.load_db()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)

    def test_changed_path_reloads(self):
        db.load_db()
        other_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other_dir)
        data = make_fixture_db()
        data['generated']['snapshot'] = '2026-12-01'
        other = write_fixture_db(other_dir, data)
        with mock.patch.object(db, 'DB_PATH', other):
            loaded = db.load_db()
        self.assertEqual(loaded['generated']['snapshot'], '2026-12-01')

    def test_missing_file_raises_os_error(self):
        missing = os.path.join(self.tempdir, 'missing.json')
        with mock.patch.object(db, 'DB_PATH', missing):
            with self.assertRaises(OSError):
                db.load_db()

    def test_invalid_json_raises_value_error(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{"schema": 1, "root": ')
        with self.assertRaises(ValueError):
            db.load_db()

    def test_missing_root_raises_value_error(self):
        write_fixture_db(self.tempdir, {'schema': 1})
        with self.assertRaises(ValueError):
            db.load_db()

    def test_wrong_schema_raises_value_error(self):
        data = make_fixture_db()
        data['schema'] = 2
        write_fixture_db(self.tempdir, data)
        with self.assertRaisesRegex(ValueError, 'schema'):
            db.load_db()

    def test_failed_load_is_not_cached(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('not json')
        with self.assertRaises(ValueError):
            db.load_db()
        write_fixture_db(self.tempdir)
        self.assertEqual(db.load_db()['schema'], 1)


class TestFindNode(unittest.TestCase):
    def setUp(self):
        self.root = make_fixture_db()['root']

    def test_empty_tokens_returns_root(self):
        node, consumed, rest = db.find_node(self.root, [])
        self.assertIs(node, self.root)
        self.assertEqual(consumed, 0)
        self.assertEqual(rest, [])

    def test_service(self):
        node, consumed, rest = db.find_node(self.root, ['ec2'])
        self.assertEqual(node['path'], 'aws.ec2')
        self.assertEqual((consumed, rest), (1, []))

    def test_operation_with_options(self):
        tokens = ['ec2', 'describe-instances', '--instance-ids', 'i-1']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.ec2.describe-instances')
        self.assertEqual(consumed, 2)
        self.assertEqual(rest, ['--instance-ids', 'i-1'])

    def test_waiter(self):
        tokens = ['ec2', 'wait', 'instance-running', '--instance-ids', 'i-1']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.ec2.wait.instance-running')
        self.assertEqual(consumed, 3)
        self.assertEqual(rest, ['--instance-ids', 'i-1'])

    def test_stops_at_unknown_token(self):
        tokens = ['ec2', 'describe-nothing', 'describe-instances']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.ec2')
        self.assertEqual(consumed, 1)
        self.assertEqual(rest, ['describe-nothing', 'describe-instances'])

    def test_unknown_service_returns_root(self):
        node, consumed, rest = db.find_node(self.root, ['nope', 'list'])
        self.assertIs(node, self.root)
        self.assertEqual((consumed, rest), (0, ['nope', 'list']))

    def test_stops_at_dash_token(self):
        tokens = ['ec2', '--debug', 'describe-instances']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.ec2')
        self.assertEqual(rest, ['--debug', 'describe-instances'])

    def test_stops_at_single_dash_token(self):
        node, consumed, rest = db.find_node(self.root, ['ec2', '-h'])
        self.assertEqual(node['path'], 'aws.ec2')
        self.assertEqual((consumed, rest), (1, ['-h']))

    def test_stops_at_help(self):
        tokens = ['ec2', 'help', 'describe-instances']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.ec2')
        self.assertEqual(rest, ['help', 'describe-instances'])

    def test_stops_at_help_even_when_a_child_is_named_help(self):
        self.root['children']['help'] = {'name': 'help', 'path': 'aws.help'}
        node, consumed, rest = db.find_node(self.root, ['help'])
        self.assertIs(node, self.root)
        self.assertEqual((consumed, rest), (0, ['help']))

    def test_leaf_with_extra_tokens(self):
        tokens = ['sqs', 'list-queues', 'extra']
        node, consumed, rest = db.find_node(self.root, tokens)
        self.assertEqual(node['path'], 'aws.sqs.list-queues')
        self.assertEqual((consumed, rest), (2, ['extra']))

    def test_accepts_tuple_and_returns_list(self):
        node, consumed, rest = db.find_node(self.root, ('sqs', 'x'))
        self.assertEqual(node['path'], 'aws.sqs')
        self.assertEqual(rest, ['x'])
        self.assertIsInstance(rest, list)

    def test_does_not_modify_tokens(self):
        tokens = ['ec2', 'describe-instances']
        db.find_node(self.root, tokens)
        self.assertEqual(tokens, ['ec2', 'describe-instances'])
