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
"""Intent heuristics and snapshot URLs of the console database generator.

The generator lives in ``scripts/console_db`` (build time only).  The type
index is built from the committed ``snapshots/resource-types.txt``; nothing
here touches the network or the command tree.
"""

import os
import sys

import pytest

REPO = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
)
SCRIPTS = os.path.join(REPO, 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from console_db import heuristics, urls_from_snapshots  # noqa: E402
from console_db.overrides import BuildError  # noqa: E402

RESOURCE_TYPES = os.path.join(
    SCRIPTS, 'console_db', 'snapshots', 'resource-types.txt'
)
NAMESPACES = {
    'acm': ['CertificateManager'],
    'apigateway': ['ApiGateway'],
    'cloudformation': ['CloudFormation'],
    'cognito-idp': ['Cognito'],
    'dynamodb': ['DynamoDB'],
    'ec2': ['EC2'],
    'ecr': ['ECR'],
    'ecs': ['ECS'],
    'elbv2': ['ElasticLoadBalancingV2'],
    'events': ['Events'],
    'glue': ['Glue'],
    'iam': ['IAM'],
    'kinesis': ['Kinesis'],
    'kms': ['KMS'],
    'lambda': ['Lambda'],
    'logs': ['Logs'],
    'rds': ['RDS'],
    'route53': ['Route53'],
    's3api': ['S3', 'S3Express'],
    'secretsmanager': ['SecretsManager'],
    'sns': ['SNS'],
    'sqs': ['SQS'],
    'sts': [],
}

# (service, operation, verb, resource_type, quality)
OPERATION_CASES = [
    ('ec2', 'describe-instances', 'list', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'run-instances', 'create', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'terminate-instances', 'view', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'start-instances', 'view', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'describe-vpcs', 'list', 'AWS::EC2::VPC', 'exact'),
    ('ec2', 'create-vpc', 'create', 'AWS::EC2::VPC', 'exact'),
    ('ec2', 'describe-subnets', 'list', 'AWS::EC2::Subnet', 'exact'),
    ('ec2', 'describe-volumes', 'list', 'AWS::EC2::Volume', 'exact'),
    ('ec2', 'attach-volume', 'view', 'AWS::EC2::Volume', 'exact'),
    ('ec2', 'create-key-pair', 'create', 'AWS::EC2::KeyPair', 'exact'),
    (
        'ec2',
        'describe-security-groups',
        'list',
        'AWS::EC2::SecurityGroup',
        'exact',
    ),
    (
        'ec2',
        'describe-instance-status',
        'list',
        'AWS::EC2::Instance',
        'fuzzy',
    ),
    ('ec2', 'describe-tags', 'home', None, 'none'),
    ('lambda', 'get-function', 'list', 'AWS::Lambda::Function', 'exact'),
    ('lambda', 'list-functions', 'list', 'AWS::Lambda::Function', 'exact'),
    (
        'lambda',
        'get-function-configuration',
        'list',
        'AWS::Lambda::Function',
        'fuzzy',
    ),
    ('lambda', 'create-function', 'create', 'AWS::Lambda::Function', 'exact'),
    ('lambda', 'delete-function', 'view', 'AWS::Lambda::Function', 'exact'),
    ('lambda', 'list-aliases', 'list', 'AWS::Lambda::Alias', 'exact'),
    (
        'lambda',
        'publish-layer-version',
        'view',
        'AWS::Lambda::LayerVersion',
        'exact',
    ),
    ('lambda', 'invoke', 'home', None, 'none'),
    ('iam', 'get-role', 'list', 'AWS::IAM::Role', 'exact'),
    ('iam', 'list-roles', 'list', 'AWS::IAM::Role', 'exact'),
    ('iam', 'create-user', 'create', 'AWS::IAM::User', 'exact'),
    ('iam', 'list-policies', 'list', 'AWS::IAM::Policy', 'exact'),
    (
        'iam',
        'get-instance-profile',
        'list',
        'AWS::IAM::InstanceProfile',
        'exact',
    ),
    ('s3api', 'list-buckets', 'list', 'AWS::S3::Bucket', 'exact'),
    ('s3api', 'create-bucket', 'create', 'AWS::S3::Bucket', 'exact'),
    ('s3api', 'get-bucket-policy', 'list', 'AWS::S3::BucketPolicy', 'exact'),
    ('s3api', 'put-bucket-policy', 'view', 'AWS::S3::BucketPolicy', 'exact'),
    ('sqs', 'get-queue-url', 'list', 'AWS::SQS::Queue', 'fuzzy'),
    ('sqs', 'list-queues', 'list', 'AWS::SQS::Queue', 'exact'),
    ('sqs', 'create-queue', 'create', 'AWS::SQS::Queue', 'exact'),
    ('sqs', 'send-message', 'home', None, 'none'),
    ('dynamodb', 'describe-table', 'list', 'AWS::DynamoDB::Table', 'exact'),
    ('dynamodb', 'list-tables', 'list', 'AWS::DynamoDB::Table', 'exact'),
    ('dynamodb', 'create-table', 'create', 'AWS::DynamoDB::Table', 'exact'),
    ('dynamodb', 'query', 'home', None, 'none'),
    ('dynamodb', 'scan', 'home', None, 'none'),
    ('logs', 'describe-log-groups', 'list', 'AWS::Logs::LogGroup', 'exact'),
    ('logs', 'create-log-group', 'create', 'AWS::Logs::LogGroup', 'exact'),
    (
        'logs',
        'describe-log-streams',
        'list',
        'AWS::Logs::LogStream',
        'exact',
    ),
    (
        'cloudformation',
        'describe-stacks',
        'list',
        'AWS::CloudFormation::Stack',
        'exact',
    ),
    (
        'cloudformation',
        'create-stack',
        'create',
        'AWS::CloudFormation::Stack',
        'exact',
    ),
    (
        'cloudformation',
        'list-stack-sets',
        'list',
        'AWS::CloudFormation::StackSet',
        'exact',
    ),
    ('ecs', 'describe-services', 'list', 'AWS::ECS::Service', 'exact'),
    ('ecs', 'update-service', 'view', 'AWS::ECS::Service', 'exact'),
    ('ecs', 'list-clusters', 'list', 'AWS::ECS::Cluster', 'exact'),
    (
        'ecs',
        'register-task-definition',
        'create',
        'AWS::ECS::TaskDefinition',
        'exact',
    ),
    ('kms', 'describe-key', 'list', 'AWS::KMS::Key', 'exact'),
    ('kms', 'create-key', 'create', 'AWS::KMS::Key', 'exact'),
    ('kms', 'list-aliases', 'list', 'AWS::KMS::Alias', 'exact'),
    ('rds', 'describe-db-instances', 'list', 'AWS::RDS::DBInstance', 'exact'),
    ('rds', 'reboot-db-instance', 'view', 'AWS::RDS::DBInstance', 'exact'),
    ('rds', 'create-db-cluster', 'create', 'AWS::RDS::DBCluster', 'exact'),
    ('sns', 'list-topics', 'list', 'AWS::SNS::Topic', 'exact'),
    ('sns', 'create-topic', 'create', 'AWS::SNS::Topic', 'exact'),
    ('sns', 'publish', 'home', None, 'none'),
    (
        'cognito-idp',
        'list-user-pools',
        'list',
        'AWS::Cognito::UserPool',
        'exact',
    ),
    (
        'cognito-idp',
        'batch-get-user-pools',
        'list',
        'AWS::Cognito::UserPool',
        'exact',
    ),
    (
        'acm',
        'request-certificate',
        'create',
        'AWS::CertificateManager::Certificate',
        'exact',
    ),
    (
        'acm',
        'add-tags-to-certificate',
        'view',
        'AWS::CertificateManager::Certificate',
        'fuzzy',
    ),
    (
        'acm',
        'list-tags-for-certificate',
        'list',
        'AWS::CertificateManager::Certificate',
        'fuzzy',
    ),
    (
        'apigateway',
        'get-rest-apis',
        'list',
        'AWS::ApiGateway::RestApi',
        'exact',
    ),
    (
        'apigateway',
        'get-resource',
        'list',
        'AWS::ApiGateway::Resource',
        'exact',
    ),
    ('apigateway', 'tag-resource', 'home', None, 'none'),
    ('apigateway', 'list-tags-for-resource', 'home', None, 'none'),
    (
        'secretsmanager',
        'get-secret-value',
        'list',
        'AWS::SecretsManager::Secret',
        'fuzzy',
    ),
    (
        'secretsmanager',
        'rotate-secret',
        'view',
        'AWS::SecretsManager::Secret',
        'exact',
    ),
    (
        'route53',
        'list-hosted-zones-by-name',
        'list',
        'AWS::Route53::HostedZone',
        'fuzzy',
    ),
    (
        'elbv2',
        'describe-load-balancers',
        'list',
        'AWS::ElasticLoadBalancingV2::LoadBalancer',
        'exact',
    ),
    ('events', 'list-rules', 'list', 'AWS::Events::Rule', 'exact'),
    ('ecr', 'describe-repositories', 'list', 'AWS::ECR::Repository', 'exact'),
    ('glue', 'get-tables', 'list', 'AWS::Glue::Table', 'exact'),
    ('kinesis', 'list-streams', 'list', 'AWS::Kinesis::Stream', 'exact'),
    ('sts', 'get-caller-identity', 'home', None, 'none'),
]

# (service, waiter, resource_type, quality)
WAITER_CASES = [
    ('ec2', 'instance-running', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'instance-status-ok', 'AWS::EC2::Instance', 'exact'),
    ('ec2', 'vpc-available', 'AWS::EC2::VPC', 'exact'),
    (
        'cloudformation',
        'stack-create-complete',
        'AWS::CloudFormation::Stack',
        'exact',
    ),
    ('dynamodb', 'table-not-exists', 'AWS::DynamoDB::Table', 'exact'),
    ('ecs', 'services-stable', 'AWS::ECS::Service', 'exact'),
    ('lambda', 'function-active-v2', 'AWS::Lambda::Function', 'exact'),
    ('rds', 'db-instance-available', 'AWS::RDS::DBInstance', 'exact'),
    ('ec2', 'password-data-available', None, 'none'),
]


@pytest.fixture(scope='module')
def index():
    with open(RESOURCE_TYPES, encoding='utf-8') as f:
        types = [line.strip() for line in f if line.strip()]
    return heuristics.build_type_index(types)


def _service(name):
    return {
        'name': name,
        'tier': 1,
        'kind': 'service',
        'console': {
            'slug': name,
            'scope': 'regional',
            'namespaces': NAMESPACES[name],
        },
    }


def _node(name, kind='operation', args=None):
    return {'name': name, 'kind': kind, '_args': args or {}}


def _args(*names, required=(), lists=()):
    return {
        name: {
            'required': name in required,
            'list': name in lists,
            'positional': False,
        }
        for name in names
    }


def test_at_least_sixty_operation_cases():
    assert len(OPERATION_CASES) >= 60


@pytest.mark.parametrize(
    'service, operation, verb, resource_type, quality',
    OPERATION_CASES,
    ids=[f'{c[0]}.{c[1]}' for c in OPERATION_CASES],
)
def test_operation_intent(
    index, service, operation, verb, resource_type, quality
):
    intent, got_quality = heuristics.derive_intent(
        _node(operation), _service(service), index
    )
    assert (intent['verb'], intent.get('resource_type'), got_quality) == (
        verb,
        resource_type,
        quality,
    )


@pytest.mark.parametrize(
    'service, waiter, resource_type, quality',
    WAITER_CASES,
    ids=[f'{c[0]}.wait.{c[1]}' for c in WAITER_CASES],
)
def test_waiter_intent(index, service, waiter, resource_type, quality):
    intent, got_quality = heuristics.derive_intent(
        _node(waiter, kind='waiter'), _service(service), index
    )
    expected_verb = 'view' if resource_type else 'home'
    assert (intent['verb'], intent.get('resource_type'), got_quality) == (
        expected_verb,
        resource_type,
        quality,
    )


def test_resource_types_list_accepted_directly():
    intent, quality = heuristics.derive_intent(
        _node('describe-instances'),
        _service('ec2'),
        ['AWS::EC2::Instance', 'AWS::EC2::VPC'],
    )
    assert intent['resource_type'] == 'AWS::EC2::Instance'
    assert quality == 'exact'


def test_service_without_namespaces_is_home(index):
    intent, quality = heuristics.derive_intent(
        _node('describe-instances'), _service('sts'), index
    )
    assert intent == {'verb': 'home', 'resource_type': None, 'id_args': []}
    assert quality == 'none'


def test_first_listed_namespace_wins():
    types = ['AWS::Alpha::Thing', 'AWS::Beta::Thing']
    service = {'console': {'namespaces': ['Beta', 'Alpha']}}
    intent, _ = heuristics.derive_intent(_node('get-thing'), service, types)
    assert intent['resource_type'] == 'AWS::Beta::Thing'


def test_other_kinds_get_no_intent(index):
    assert heuristics.derive_intent(
        _node('ls', kind='subcommand'), _service('ec2'), index
    ) == (None, None)


@pytest.mark.parametrize(
    'operation, verb, noun',
    [
        ('describe-instances', 'list', ['instances']),
        ('batch-get-item', 'list', ['item']),
        ('batch-delete-items', 'view', ['items']),
        ('admin-get-user', 'view', ['user']),
        ('create-stack', 'create', ['stack']),
        ('import-key-pair', 'create', ['key', 'pair']),
        ('wibble-widget', 'view', ['widget']),
        ('lookup-events', 'list', ['events']),
    ],
)
def test_split_verb(operation, verb, noun):
    assert heuristics.split_verb(operation) == (verb, noun)


@pytest.mark.parametrize(
    'word, singular',
    [
        ('policies', 'policy'),
        ('addresses', 'address'),
        ('processes', 'process'),
        ('boxes', 'box'),
        ('branches', 'branch'),
        ('meshes', 'mesh'),
        ('instances', 'instance'),
        ('indices', 'index'),
        ('aliases', 'alias'),
        ('analyses', 'analysis'),
        ('statuses', 'status'),
        ('status', 'status'),
        ('series', 'series'),
        ('apis', 'api'),
        ('caches', 'cache'),
        ('access', 'access'),
        ('analysis', 'analysis'),
    ],
)
def test_singularize(word, singular):
    assert heuristics.singularize(word) == singular


@pytest.mark.parametrize(
    'waiter, noun',
    [
        ('instance-running', ['instance']),
        ('stack-create-complete', ['stack']),
        ('bucket-not-exists', ['bucket']),
        ('instance-in-service', ['instance']),
        ('function-active-v2', ['function']),
    ],
)
def test_waiter_noun(waiter, noun):
    assert heuristics.waiter_noun(waiter) == noun


@pytest.mark.parametrize(
    'args, noun, expected',
    [
        (
            _args('instance-ids', 'filters', 'dry-run', 'max-results'),
            ['instance'],
            ['--instance-ids'],
        ),
        (
            _args('function-name', 'qualifier'),
            ['function'],
            ['--function-name'],
        ),
        (
            _args('services', 'cluster', lists=('services',)),
            ['service'],
            ['--services'],
        ),
        (
            _args('name', 'role-arn', required=('name',)),
            ['topic'],
            ['--name'],
        ),
        (
            _args('user-pool-id', 'username', required=('user-pool-id',)),
            ['user'],
            ['--user-pool-id'],
        ),
        (
            _args('log-group-name-prefix', 'log-group-identifiers'),
            ['log', 'group'],
            [],
        ),
        (
            _args('db-instance-identifier', 'next-token'),
            ['db', 'instance'],
            ['--db-instance-identifier'],
        ),
        (
            _args('queue-name', 'queue-owner-aws-account-id'),
            ['queue'],
            ['--queue-name'],
        ),
        (
            _args(
                'load-balancer-arns', 'names', lists=('load-balancer-arns',)
            ),
            ['load', 'balancer'],
            ['--load-balancer-arns'],
        ),
        (
            _args('cli-input-json', 'generate-cli-skeleton', 'page-size'),
            ['thing'],
            [],
        ),
        (
            _args('id', 'arn', 'thing-id', required=('id',)),
            ['thing'],
            ['--thing-id', '--id', '--arn'],
        ),
        (
            _args('resource-arn', 'tag-keys', required=('resource-arn',)),
            ['certificate'],
            ['--resource-arn'],
        ),
    ],
)
def test_id_args(args, noun, expected):
    assert heuristics.id_args_for(args, noun) == expected


def test_id_args_from_derive_intent(index):
    node = _node(
        'describe-instances',
        args=_args(
            'instance-ids', 'filters', 'dry-run', lists=('instance-ids',)
        ),
    )
    intent, _ = heuristics.derive_intent(node, _service('ec2'), index)
    assert intent['id_args'] == ['--instance-ids']


# --- urls_from_snapshots -------------------------------------------------

EC2_HOME = 'https://{region}.{host}/ec2/home?region={region}'
PROBE = 'https://us-west-2.console.aws.amazon.com'


@pytest.mark.parametrize(
    'status, url, deep',
    [
        ('302', PROBE + '/ec2/home?region=us-west-2#Instances:', True),
        ('302', PROBE + '/ec2/home?region=us-west-2', False),
        ('302', PROBE + '/ecs/v2/home', False),
        ('302', 'https://console.aws.amazon.com/console/home', False),
        (
            '302',
            'https://console.aws.amazon.com/s3/buckets?region=us-west-2',
            True,
        ),
        ('404', PROBE + '/ec2/home?region=us-west-2#Instances:', False),
        ('302', PROBE + '/ec2/home?region=us-west-2&tab=x', True),
        (
            '302',
            'https://$region}.quicksight.aws.amazon.com/sn/start/a',
            False,
        ),
    ],
)
def test_is_deep(status, url, deep):
    assert urls_from_snapshots.is_deep(status, url) is deep


@pytest.mark.parametrize(
    'redirect, id_arg, template',
    [
        (
            PROBE
            + '/ec2/home?region=us-west-2#InstanceDetails:instanceId=zz9idzz9',
            '--instance-ids',
            EC2_HOME + '#InstanceDetails:instanceId={id}',
        ),
        (
            PROBE + '/ecs/v2/redirect?arn=zz9idzz9&region=us-west-2',
            '--services',
            'https://{region}.{host}/ecs/v2/redirect?arn={id:query}&region={region}',
        ),
        (
            PROBE + '/ecs/v2/redirect?arn=zz9idzz9&region=us-west-2',
            '--service-arn',
            'https://{region}.{host}/ecs/v2/redirect?arn={id:raw}&region={region}',
        ),
        (
            PROBE + '/acm-pca/home?region=us-west-2#/details?arn=zz9idzz9',
            '--name',
            'https://{region}.{host}/acm-pca/home?region={region}#/details?arn={id}',
        ),
        (
            'https://console.aws.amazon.com/iam/home#/roles/details/zz9idzz9',
            '--role-name',
            'https://{host}/iam/home#/roles/details/{id}',
        ),
        (
            'https://console.aws.amazon.com/iam/home#/roles/details/zz9idzz9',
            '--role-arns',
            'https://{host}/iam/home#/roles/details/{id:raw}',
        ),
    ],
)
def test_detail_template(redirect, id_arg, template):
    assert urls_from_snapshots.detail_template(redirect, id_arg) == template


def test_detail_template_with_leftover_sentinel_raises():
    with pytest.raises(BuildError):
        urls_from_snapshots.detail_template(
            PROBE + '/x/home?region=us-west-2#a=zz9idzz9&b=zz9', '--id'
        )


TYPES_ROWS = [
    {
        'resource_type': 'AWS::EC2::Instance',
        'list_status': '302',
        'list_redirect': PROBE + '/ec2/home?region=us-west-2#Instances:',
        'create_status': '302',
        'create_redirect': PROBE
        + '/ec2/home?region=us-west-2#LaunchInstances:',
    },
    {
        'resource_type': 'AWS::EC2::Volume',
        'list_status': '302',
        'list_redirect': PROBE + '/ec2/home?region=us-west-2',
        'create_status': '302',
        'create_redirect': PROBE + '/ec2/home?region=us-west-2',
    },
    {
        'resource_type': 'AWS::EC2::Host',
        'list_status': '302',
        'list_redirect': PROBE + '/ec2/home?region=us-west-2#Hosts:',
        'create_status': '404',
        'create_redirect': '',
    },
]
VIEW_ROWS = [
    {
        'resource_type': 'AWS::EC2::Instance',
        'id_status': '302',
        'id_redirect': PROBE
        + '/ec2/home?region=us-west-2#InstanceDetails:instanceId=zz9idzz9',
    },
    {
        'resource_type': 'AWS::EC2::Volume',
        'id_status': '302',
        'id_redirect': PROBE + '/ec2/home?region=us-west-2#Volumes:',
    },
    {
        'resource_type': 'AWS::EC2::Host',
        'id_status': '302',
        'id_redirect': PROBE
        + '/ec2/home?region=us-west-2#HostDetails:hostId=zz9idzz9',
    },
]


def _tree(intents):
    service = {
        'name': 'ec2',
        'path': 'aws.ec2',
        'tier': 1,
        'kind': 'service',
        'url': {'best': EC2_HOME, 'source': 'resolver:service'},
        'children': {},
    }
    for name, (kind, intent) in intents.items():
        service['children'][name] = {
            'name': name,
            'path': f'aws.ec2.{name}',
            'tier': 2,
            'kind': kind,
            'intent': intent,
            'url': {
                'best': EC2_HOME,
                'source': 'service-home',
                'verified': 'home-date',
                'needs_account': False,
            },
            'children': {},
        }
    return {
        'name': 'aws',
        'path': 'aws',
        'tier': 0,
        'kind': 'root',
        'children': {'ec2': service},
    }


def _intent(verb, resource_type, id_args=()):
    return {
        'verb': verb,
        'resource_type': resource_type,
        'id_args': list(id_args),
    }


def test_assign_urls():
    instance = 'AWS::EC2::Instance'
    root = _tree(
        {
            'describe-instances': (
                'operation',
                _intent('list', instance, ['--instance-ids']),
            ),
            # A create command never gets the detail template, even with
            # an id option and a type that has one.
            'run-instances': (
                'operation',
                _intent('create', instance, ['--instance-name']),
            ),
            'import-instance': (
                'operation',
                _intent('create', 'AWS::EC2::Host', ['--host-id']),
            ),
            'describe-volumes': (
                'operation',
                _intent('list', 'AWS::EC2::Volume', ['--volume-ids']),
            ),
            'describe-tags': ('operation', _intent('home', None)),
            'ls': ('subcommand', _intent('list', instance, ['--x-id'])),
        }
    )
    urls_from_snapshots.assign_urls(
        root,
        {'types': TYPES_ROWS, 'view_by_id': VIEW_ROWS, 'services': []},
        snapshot_date='2026-11-04',
    )
    children = root['children']['ec2']['children']
    assert children['describe-instances']['url'] == {
        'best': EC2_HOME + '#Instances:',
        'with_id': EC2_HOME + '#InstanceDetails:instanceId={id}',
        'source': 'resolver:list+view',
        'verified': '2026-11-04',
        'needs_account': False,
    }
    assert children['run-instances']['url'] == {
        'best': EC2_HOME + '#LaunchInstances:',
        'source': 'resolver:create',
        'verified': '2026-11-04',
        'needs_account': False,
    }
    # No create page: the list page, still without the detail template.
    assert children['import-instance']['url'] == {
        'best': EC2_HOME + '#Hosts:',
        'source': 'resolver:list',
        'verified': '2026-11-04',
        'needs_account': False,
    }
    # No deep list page and no detail template: the home, source derived.
    assert children['describe-volumes']['url'] == {
        'best': EC2_HOME,
        'source': 'derived',
        'verified': 'home-date',
        'needs_account': False,
    }
    # No resource type, or a custom subcommand: untouched.
    assert children['describe-tags']['url']['source'] == 'service-home'
    assert children['ls']['url']['source'] == 'service-home'
