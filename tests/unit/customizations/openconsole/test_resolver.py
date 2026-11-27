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
from urllib.parse import quote_plus

from awscli.customizations.open_the_console_to_this.resolver import (
    Context,
    account_from_arn,
    domain_for_region,
    global_url,
    go_view,
    go_view_service,
    regional,
    resolve,
    valid,
)
from awscli.testutils import unittest

REGION = 'us-west-2'


def ctx(region=REGION, partition='aws'):
    return Context(region, partition)


class TestDomain(unittest.TestCase):
    def test_partition_routing(self):
        cases = (
            ('us-east-1', 'console.aws.amazon.com'),
            ('eu-central-1', 'console.aws.amazon.com'),
            ('ap-southeast-2', 'console.aws.amazon.com'),
            ('us-gov-west-1', 'console.amazonaws-us-gov.com'),
            ('us-gov-east-1', 'console.amazonaws-us-gov.com'),
            ('cn-north-1', 'console.amazonaws.cn'),
            ('cn-northwest-1', 'console.amazonaws.cn'),
        )
        for region, host in cases:
            self.assertEqual(domain_for_region(region), host, region)


class TestUrlBuilders(unittest.TestCase):
    def test_regional_uses_a_region_subdomain(self):
        tail = (
            'ec2/home?region=us-east-1#InstanceDetails:instanceId=i-0abc123'
        )
        self.assertEqual(
            regional('us-east-1', tail),
            'https://us-east-1.console.aws.amazon.com/' + tail,
        )
        self.assertEqual(
            regional('us-gov-west-1', 'ec2/home?region=us-gov-west-1'),
            'https://us-gov-west-1.console.amazonaws-us-gov.com/'
            'ec2/home?region=us-gov-west-1',
        )
        self.assertEqual(
            regional('cn-north-1', 's3/buckets/my-bucket'),
            'https://cn-north-1.console.amazonaws.cn/s3/buckets/my-bucket',
        )

    def test_global_omits_the_region_subdomain(self):
        self.assertEqual(
            global_url('us-east-1', 'iam/home#/roles/details/my-role'),
            'https://console.aws.amazon.com/iam/home#/roles/details/my-role',
        )
        self.assertEqual(
            global_url('eu-west-1', 's3/buckets/my-bucket'),
            'https://console.aws.amazon.com/s3/buckets/my-bucket',
        )
        self.assertEqual(
            global_url('us-gov-west-1', 'iam/home'),
            'https://console.amazonaws-us-gov.com/iam/home',
        )
        self.assertEqual(
            global_url('cn-north-1', 'iam/home'),
            'https://console.amazonaws.cn/iam/home',
        )

    def test_partition_selects_the_host(self):
        self.assertEqual(
            regional('us-east-1', 'ec2/home', 'aws-cn'),
            'https://us-east-1.console.amazonaws.cn/ec2/home',
        )

    def test_go_view_query_escapes_the_arn(self):
        arns = (
            'arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123',
            'arn:aws-us-gov:ec2:us-gov-west-1:123456789012:instance/i-0abc',
            'arn:aws-cn:ec2:cn-north-1:123456789012:instance/i-0abc123',
            'arn:aws:codeartifact:eu-west-1:123456789012:repository/'
            'dom ain/repo name',
        )
        regions = (
            'us-east-1',
            'us-gov-west-1',
            'cn-north-1',
            'eu-west-1',
        )
        for region, arn in zip(regions, arns):
            self.assertEqual(
                go_view(region, arn),
                global_url(region, 'go/view?arn=' + quote_plus(arn)),
            )


class TestAccountFromArn(unittest.TestCase):
    def test_account_field(self):
        cases = (
            (
                'arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123',
                '123456789012',
            ),
            ('arn:aws:iam::123456789012:role/my-role', '123456789012'),
            ('arn:aws:s3:::my-bucket', ''),
            ('not-an-arn', ''),
            ('', ''),
            ('arn:aws:ec2', ''),
        )
        for arn, account in cases:
            self.assertEqual(account_from_arn(arn), account, arn)


class TestValid(unittest.TestCase):
    def test_accepts_console_hosts(self):
        urls = (
            'https://console.aws.amazon.com/iam/home',
            'https://us-east-1.console.aws.amazon.com/ec2/home'
            '?region=us-east-1',
            'https://eu-central-1.console.aws.amazon.com/s3/buckets/x',
            'https://console.amazonaws-us-gov.com/iam/home',
            'https://us-gov-west-1.console.amazonaws-us-gov.com/ec2/home',
            'https://console.amazonaws.cn/iam/home',
            'https://cn-north-1.console.amazonaws.cn/ec2/home',
        )
        for url in urls:
            self.assertTrue(valid(url), url)

    def test_rejects_non_console_or_insecure_urls(self):
        urls = (
            'http://console.aws.amazon.com/iam/home',
            'https://evil.example.com/iam/home',
            'https://console.aws.amazon.com.evil.example.com/x',
            '',
            'not-a-url-at-all',
            'https://.console.aws.amazon.com/ec2/home',
            'https://.console.amazonaws-us-gov.com/ec2/home',
            'https://.console.amazonaws.cn/ec2/home',
        )
        for url in urls:
            self.assertFalse(valid(url), url)


class TestResolve(unittest.TestCase):
    def test_s3_ls_opens_the_bucket_list(self):
        decision = resolve('s3', ['ls'], ctx())
        self.assertEqual(
            decision.url,
            f'https://console.aws.amazon.com/s3/buckets?region={REGION}',
        )
        self.assertEqual(decision.node_path, 'aws.s3.ls')
        self.assertEqual(decision.source, 'console')
        self.assertEqual(decision.verb, 'list')

    def test_s3_ls_opens_a_prefix(self):
        decision = resolve('s3', ['ls', 's3://photos/2026/'], ctx())
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/s3/buckets/photos'
            f'?region={REGION}&prefix=2026%2F&showversions=false',
        )
        self.assertEqual(
            decision.params, {'bucket': 'photos', 'prefix': '2026/'}
        )

    def test_s3_cp_opens_the_target_object(self):
        decision = resolve(
            's3', ['cp', 'local.txt', 's3://photos/2026/pic.jpg'], ctx()
        )
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/s3/object/photos'
            f'?region={REGION}&prefix=2026%2Fpic.jpg',
        )

    def test_unknown_s3_subcommand_uses_the_bucket_list(self):
        decision = resolve('s3', ['not-a-subcommand'], ctx())
        self.assertEqual(
            decision.url,
            f'https://console.aws.amazon.com/s3/buckets?region={REGION}',
        )

    def test_ec2_instance(self):
        decision = resolve(
            'ec2',
            ['describe-instances', '--instance-ids', 'i-0123456789abcdef0'],
            ctx(),
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#InstanceDetails:instanceId=i-0123456789abcdef0',
        )

    def test_several_instance_ids_open_the_filtered_list(self):
        decision = resolve(
            'ec2',
            ['describe-instances', '--instance-ids', 'i-0aaa', 'i-0bbb'],
            ctx(),
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#Instances:instanceId=i-0aaa,i-0bbb',
        )
        self.assertEqual(decision.verb, 'list')

    def test_describe_images_without_ids_opens_the_image_list(self):
        decision = resolve('ec2', ['describe-images'], ctx())
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#Images:',
        )

    def test_several_image_ids_open_the_filtered_image_list(self):
        decision = resolve(
            'ec2',
            ['describe-images', '--image-ids', 'ami-aaa', 'ami-bbb'],
            ctx(),
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#Images:imageId=ami-aaa,ami-bbb',
        )

    def test_one_image_opens_the_image(self):
        decision = resolve(
            'ec2', ['describe-images', '--image-ids', 'ami-abc'], ctx()
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#ImageDetails:imageId=ami-abc',
        )

    def test_create_vpc_opens_the_vpc_list(self):
        decision = resolve(
            'ec2', ['create-vpc', '--cidr-block', '10.1.0.0/16'], ctx()
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/vpc/home'
            f'?region={REGION}#vpcs:',
        )

    def test_several_vpc_ids_open_the_filtered_vpc_list(self):
        decision = resolve(
            'ec2',
            ['describe-vpcs', '--vpc-ids', 'vpc-aaa', 'vpc-bbb'],
            ctx(),
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/vpc/home'
            f'?region={REGION}#vpcs:VpcId=vpc-aaa,vpc-bbb',
        )

    def test_create_snapshot_opens_the_snapshot_list(self):
        decision = resolve(
            'ec2', ['create-snapshot', '--volume-id', 'vol-abc'], ctx()
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}#Snapshots:',
        )

    def test_instance_types_stay_on_the_ec2_home(self):
        decision = resolve('ec2', ['describe-instance-types'], ctx())
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/ec2/home'
            f'?region={REGION}',
        )

    def test_several_functions_open_the_filtered_list(self):
        decision = resolve(
            'lambda',
            ['list-functions'],
            ctx(),
            response={
                'Functions': [
                    {'FunctionName': 'alpha'},
                    {'FunctionName': 'beta'},
                ]
            },
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/lambda/home'
            f'?region={REGION}#/functions?fo=or'
            '&k0=functionName&o0=%3D&v0=alpha'
            '&k1=functionName&o1=%3D&v1=beta',
        )

    def test_several_roles_open_the_filtered_list(self):
        decision = resolve(
            'iam',
            ['list-roles'],
            ctx(),
            response={
                'Roles': [{'RoleName': 'Admin'}, {'RoleName': 'ReadOnly'}]
            },
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/iam/home#/roles?fo=or'
            '&k0=roleName&o0=%3D&v0=Admin'
            '&k1=roleName&o1=%3D&v1=ReadOnly',
        )

    def test_several_queues_open_the_filtered_list(self):
        first = 'https://sqs.us-west-2.amazonaws.com/123/a'
        second = 'https://sqs.us-west-2.amazonaws.com/123/b'
        decision = resolve(
            'sqs',
            ['list-queues'],
            ctx(),
            response={'QueueUrls': [first, second]},
            after_run=True,
        )
        self.assertIn('#/queues?fo=or', decision.url)
        self.assertIn('k0=queueUrl', decision.url)
        self.assertIn('v0=' + quote_plus(first), decision.url)
        self.assertIn('v1=' + quote_plus(second), decision.url)

    def test_several_stacks_open_the_filtered_list(self):
        decision = resolve(
            'cloudformation',
            ['list-stacks'],
            ctx(),
            response={
                'Stacks': [{'StackName': 'one'}, {'StackName': 'two'}]
            },
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/cloudformation/home'
            f'?region={REGION}#stacks?fo=or'
            '&k0=stackName&o0=%3D&v0=one'
            '&k1=stackName&o1=%3D&v1=two',
        )

    def test_several_log_groups_open_the_filtered_list(self):
        decision = resolve(
            'logs',
            ['describe-log-groups'],
            ctx(),
            response={
                'logGroups': [
                    {'logGroupName': 'app'},
                    {'logGroupName': 'api'},
                ]
            },
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/cloudwatch/home'
            f'?region={REGION}#logsV2:log-groups'
            '$3FlogGroupNameFilter$3Dapp,api',
        )

    def test_several_buckets_open_the_filtered_list(self):
        decision = resolve(
            's3api',
            ['list-buckets'],
            ctx(),
            response={
                'Buckets': [{'Name': 'photos'}, {'Name': 'logs'}]
            },
            after_run=True,
        )
        self.assertIn('/s3/buckets?region=', decision.url)
        self.assertIn('fo=or', decision.url)
        self.assertIn('k0=name', decision.url)
        self.assertIn('v0=photos', decision.url)
        self.assertIn('v1=logs', decision.url)

    def test_several_tables_open_the_filtered_list(self):
        decision = resolve(
            'dynamodb',
            ['list-tables'],
            ctx(),
            response={'TableNames': ['Music', 'Orders']},
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/dynamodbv2/home'
            f'?region={REGION}#table?fo=or'
            '&k0=tableName&o0=%3D&v0=Music'
            '&k1=tableName&o1=%3D&v1=Orders',
        )

    def test_lambda_function_named_help(self):
        decision = resolve(
            'lambda',
            ['get-function', '--function-name', 'help'],
            ctx(),
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/lambda/home'
            f'?region={REGION}#/functions/help',
        )

    def test_iam_role_is_global(self):
        decision = resolve(
            'iam', ['get-role', '--role-name', 'Admin'], ctx()
        )
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/iam/home#/roles/details/Admin',
        )

    def test_arn_uses_go_view(self):
        arn = 'arn:aws:kms:us-west-2:123456789012:key/abcd-1234'
        decision = resolve(
            'kms', ['describe-key', '--key-id', arn], ctx()
        )
        self.assertEqual(decision.url, go_view(REGION, arn, 'aws'))
        self.assertEqual(decision.source, 'go-view')

    def test_builder_wins_over_an_arn_in_the_response(self):
        arn = f'arn:aws:dynamodb:{REGION}:123456789012:table/Music'
        decision = resolve(
            'dynamodb',
            ['create-table', '--table-name', 'Music'],
            ctx(),
            response={'Table': {'TableName': 'Music', 'TableArn': arn}},
            after_run=True,
        )
        self.assertIn('#table?name=Music', decision.url)
        self.assertNotIn('go/view', decision.url)

    def test_unknown_command_uses_go_view_service(self):
        decision = resolve('not-a-service', ['do-thing'], ctx())
        self.assertEqual(
            decision.url, go_view_service(REGION, 'not-a-service', 'aws')
        )
        self.assertEqual(decision.source, 'fallback')

    def test_configure_opens_the_console_home(self):
        decision = resolve('configure', ['list'], ctx())
        self.assertEqual(
            decision.url,
            f'https://console.aws.amazon.com/console/home?region={REGION}',
        )

    def test_govcloud_ec2_home(self):
        decision = resolve('ec2', [], ctx('us-gov-west-1', 'aws-us-gov'))
        self.assertEqual(
            decision.url,
            'https://us-gov-west-1.console.amazonaws-us-gov.com/ec2/home'
            '?region=us-gov-west-1',
        )

    def test_account_callable_is_lazy(self):
        calls = []

        def account():
            calls.append(1)
            return '123456789012'

        context = Context(REGION, 'aws', account_id=account)
        resolve('s3', ['ls'], context)
        self.assertEqual(calls, [])
        self.assertEqual(context.account(), '123456789012')
        self.assertEqual(context.account(), '123456789012')
        self.assertEqual(calls, [1])

    def test_help_is_not_an_option_value(self):
        from awscli.customizations.open_the_console_to_this.resolver import (
            is_help,
        )

        self.assertTrue(is_help('s3', ['ls', '--recursive', 'help']))
        self.assertFalse(
            is_help('s3', ['ls', '--page-size', 'help'])
        )
        self.assertFalse(
            is_help('lambda', ['get-function', '--function-name', 'help'])
        )
