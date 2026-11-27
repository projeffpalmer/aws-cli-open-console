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
from urllib.parse import quote_plus

from awscli.customizations.openconsole.resolver import (
    MAX_URL_LENGTH,
    Context,
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
        tail = 'ec2/home?region=us-east-1#InstanceDetails:instanceId=i-0abc123'
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

    def test_several_roles_open_the_role_list(self):
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
            decision.url, 'https://console.aws.amazon.com/iam/home#/roles'
        )

    def test_several_queues_open_the_queue_list(self):
        first = 'https://sqs.us-west-2.amazonaws.com/123/a'
        second = 'https://sqs.us-west-2.amazonaws.com/123/b'
        decision = resolve(
            'sqs',
            ['list-queues'],
            ctx(),
            response={'QueueUrls': [first, second]},
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/sqs/v3/home'
            f'?region={REGION}#/queues',
        )

    def test_several_stacks_open_the_stack_list(self):
        decision = resolve(
            'cloudformation',
            ['list-stacks'],
            ctx(),
            response={'Stacks': [{'StackName': 'one'}, {'StackName': 'two'}]},
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://{REGION}.console.aws.amazon.com/cloudformation/home'
            f'?region={REGION}#stacks',
        )

    def test_several_log_groups_open_the_log_group_list(self):
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
            f'?region={REGION}#logsV2:log-groups',
        )

    def test_several_buckets_open_the_bucket_list(self):
        decision = resolve(
            's3api',
            ['list-buckets'],
            ctx(),
            response={'Buckets': [{'Name': 'photos'}, {'Name': 'logs'}]},
            after_run=True,
        )
        self.assertEqual(
            decision.url,
            f'https://console.aws.amazon.com/s3/buckets?region={REGION}',
        )

    def test_several_tables_open_the_table_list(self):
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
            f'?region={REGION}#table',
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
        decision = resolve('iam', ['get-role', '--role-name', 'Admin'], ctx())
        self.assertEqual(
            decision.url,
            'https://console.aws.amazon.com/iam/home#/roles/details/Admin',
        )

    def test_arn_uses_go_view(self):
        arn = 'arn:aws:kms:us-west-2:123456789012:key/abcd-1234'
        decision = resolve('kms', ['describe-key', '--key-id', arn], ctx())
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

    def test_help_is_not_an_option_value(self):
        from awscli.customizations.openconsole.resolver import (
            is_help,
        )

        self.assertTrue(is_help('s3', ['ls', '--recursive', 'help']))
        self.assertFalse(is_help('s3', ['ls', '--page-size', 'help']))
        self.assertFalse(
            is_help('lambda', ['get-function', '--function-name', 'help'])
        )


HOME = f'https://{REGION}.console.aws.amazon.com'
EC2 = f'{HOME}/ec2/home?region={REGION}'
VPC = f'{HOME}/vpc/home?region={REGION}'
LAMBDA = f'{HOME}/lambda/home?region={REGION}'
DYNAMODB = f'{HOME}/dynamodbv2/home?region={REGION}'
CLOUDFORMATION = f'{HOME}/cloudformation/home?region={REGION}'
SQS = f'{HOME}/sqs/v3/home?region={REGION}'
LOGS = f'{HOME}/cloudwatch/home?region={REGION}'
IAM = 'https://console.aws.amazon.com/iam/home'
S3 = 'https://console.aws.amazon.com/s3'
QUEUE = 'https://sqs.us-west-2.amazonaws.com/123456789012/orders'
LOG_GROUP_ARN = 'arn:aws:logs:us-west-2:123456789012:log-group:/aws/lambda/f'


def url_for(command, response=None, after_run=False):
    service, *remaining = command.split()
    decision = resolve(
        service, remaining, ctx(), response=response, after_run=after_run
    )
    return decision.url


class BasePagesTest(unittest.TestCase):
    def assert_pages(self, cases):
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(url_for(command), expected)


class TestEc2Pages(BasePagesTest):
    def test_resource_pages_use_the_routes_the_console_has(self):
        self.assert_pages(
            [
                (
                    'ec2 describe-network-interfaces '
                    '--network-interface-ids eni-0abc',
                    EC2 + '#NetworkInterface:networkInterfaceId=eni-0abc',
                ),
                (
                    'ec2 describe-key-pairs --key-names my-key',
                    EC2 + '#KeyPairs:keyName=my-key',
                ),
                (
                    'ec2 describe-addresses --allocation-ids eipalloc-0abc',
                    EC2 + '#ElasticIpDetails:AllocationId=eipalloc-0abc',
                ),
            ]
        )


class TestUrlLength(unittest.TestCase):
    def instances(self, count):
        return {
            'Reservations': [
                {'Instances': [{'InstanceId': f'i-{index:017x}'}]}
                for index in range(count)
            ]
        }

    def test_filter_is_kept_while_the_url_fits(self):
        url = url_for('ec2 describe-instances', self.instances(3), True)
        self.assertTrue(url.startswith(EC2 + '#Instances:instanceId=i-'))
        self.assertLessEqual(len(url), MAX_URL_LENGTH)

    def test_too_many_instances_open_the_unfiltered_list(self):
        url = url_for('ec2 describe-instances', self.instances(500), True)
        self.assertEqual(url, EC2 + '#Instances:')

    def test_too_many_launched_instances_open_the_unfiltered_list(self):
        response = {
            'Instances': [
                {'InstanceId': f'i-{index:017x}'} for index in range(500)
            ]
        }
        url = url_for('ec2 run-instances --image-id ami-1', response, True)
        self.assertEqual(url, EC2 + '#Instances:')

    def test_too_many_vpcs_open_the_unfiltered_list(self):
        response = {
            'Vpcs': [{'VpcId': f'vpc-{index:017x}'} for index in range(500)]
        }
        url = url_for('ec2 describe-vpcs', response, True)
        self.assertEqual(url, VPC + '#vpcs:')

    def test_too_many_functions_open_the_unfiltered_list(self):
        response = {
            'Functions': [
                {'FunctionName': f'function-number-{index}'}
                for index in range(500)
            ]
        }
        url = url_for('lambda list-functions', response, True)
        self.assertEqual(url, LAMBDA + '#/functions')

    def test_no_page_is_longer_than_the_limit(self):
        # Each of these characters takes three in the URL.
        key = '{' * 700
        decision = resolve('s3', ['cp', 'f.txt', f's3://photos/{key}'], ctx())
        self.assertEqual(decision.url, f'{S3}/buckets?region={REGION}')
        self.assertLessEqual(len(decision.url), MAX_URL_LENGTH)


class TestResponseNamesOtherResources(unittest.TestCase):
    def test_listed_objects_do_not_replace_the_bucket(self):
        response = {
            'Contents': [{'Key': 'a.txt'}, {'Key': 'dir/b.txt'}],
            'Name': 'photos',
            'Prefix': '',
            'KeyCount': 2,
        }
        self.assertEqual(
            url_for('s3api list-objects-v2 --bucket photos', response, True),
            f'{S3}/buckets/photos?region={REGION}',
        )

    def test_listed_objects_keep_the_typed_prefix(self):
        response = {'Contents': [{'Key': 'dir/b.txt'}], 'Prefix': 'dir/'}
        self.assertEqual(
            url_for(
                's3api list-objects-v2 --bucket photos --prefix dir/',
                response,
                True,
            ),
            f'{S3}/buckets/photos?region={REGION}'
            '&prefix=dir%2F&showversions=false',
        )

    def test_listed_versions_do_not_replace_the_bucket(self):
        response = {'Versions': [{'Key': 'a.txt', 'VersionId': 'v1'}]}
        self.assertEqual(
            url_for(
                's3api list-object-versions --bucket photos', response, True
            ),
            f'{S3}/buckets/photos?region={REGION}',
        )

    def test_a_rule_prefix_does_not_replace_the_bucket(self):
        response = {
            'ReplicationConfiguration': {
                'Rules': [
                    {
                        'Prefix': 'x/',
                        'Destination': {'Bucket': 'arn:aws:s3:::other'},
                    }
                ]
            }
        }
        self.assertEqual(
            url_for(
                's3api get-bucket-replication --bucket photos', response, True
            ),
            f'{S3}/buckets/photos?region={REGION}',
        )

    def test_a_typed_key_still_opens_the_object(self):
        self.assertEqual(
            url_for('s3api head-object --bucket photos --key dir/a.txt'),
            f'{S3}/object/photos?region={REGION}&prefix=dir%2Fa.txt',
        )

    def test_listed_streams_do_not_replace_the_log_group(self):
        response = {
            'logStreams': [
                {'logStreamName': '2026/11/26/[$LATEST]aaa'},
                {'logStreamName': '2026/11/25/[$LATEST]bbb'},
            ]
        }
        self.assertEqual(
            url_for(
                'logs describe-log-streams --log-group-name /aws/lambda/f',
                response,
                True,
            ),
            LOGS + '#logsV2:log-groups/log-group/%2Faws%2Flambda%2Ff',
        )

    def test_event_streams_do_not_replace_the_log_group(self):
        response = {'events': [{'logStreamName': 's1', 'message': 'm'}]}
        self.assertEqual(
            url_for(
                'logs filter-log-events --log-group-name app', response, True
            ),
            LOGS + '#logsV2:log-groups/log-group/app',
        )

    def test_a_nested_role_does_not_replace_the_command(self):
        response = {
            'InstanceProfiles': [
                {'InstanceProfileName': 'web', 'Roles': [{'RoleName': 'r1'}]}
            ]
        }
        self.assertEqual(
            url_for('iam list-instance-profiles', response, True), IAM
        )

    def test_the_user_in_a_user_response_is_opened(self):
        response = {'User': {'UserName': 'alice'}}
        self.assertEqual(
            url_for('iam get-user', response, True),
            IAM + '#/users/details/alice',
        )


class TestS3Pages(BasePagesTest):
    def test_directory_targets_open_that_prefix(self):
        prefix = '&prefix={}&showversions=false'
        bucket = f'{S3}/buckets/photos?region={REGION}'
        self.assert_pages(
            [
                (
                    's3 sync ./dir s3://photos/backup',
                    bucket + prefix.format('backup%2F'),
                ),
                (
                    's3 sync s3://photos/a/b ./dir',
                    bucket + prefix.format('a%2Fb%2F'),
                ),
                ('s3 sync ./dir s3://photos', bucket),
                (
                    's3 cp ./dir s3://photos/dir --recursive',
                    bucket + prefix.format('dir%2F'),
                ),
                (
                    's3 mv ./dir s3://photos/a/dir --recursive',
                    bucket + prefix.format('a%2Fdir%2F'),
                ),
                (
                    's3 rm s3://photos/dir --recursive',
                    bucket + prefix.format('dir%2F'),
                ),
            ]
        )

    def test_object_and_bucket_pages(self):
        obj = f'{S3}/object/photos?region={REGION}&prefix='
        self.assert_pages(
            [
                ('s3 rm s3://photos/dir/a.txt', obj + 'dir%2Fa.txt'),
                (
                    's3 presign s3://photos/dir/a.txt --expires-in 60',
                    obj + 'dir%2Fa.txt',
                ),
                (
                    's3 website s3://photos --index-document index.html',
                    f'{S3}/buckets/photos?region={REGION}&tab=properties',
                ),
                ('s3 rb s3://photos', f'{S3}/buckets/photos?region={REGION}'),
            ]
        )

    def test_mb_without_a_bucket_opens_the_create_page(self):
        self.assertEqual(
            url_for('s3 mb'), f'{S3}/bucket/create?region={REGION}'
        )

    def test_mb_with_a_bucket_opens_the_bucket(self):
        self.assertEqual(
            url_for('s3 mb s3://photos', after_run=True),
            f'{S3}/buckets/photos?region={REGION}',
        )

    def test_a_path_named_help_is_not_a_help_request(self):
        from awscli.customizations.openconsole.resolver import is_help

        self.assertFalse(is_help('s3', ['cp', 'help', 's3://photos/help']))
        self.assertEqual(
            url_for('s3 cp help s3://photos/help'),
            f'{S3}/object/photos?region={REGION}&prefix=help',
        )
        self.assertTrue(is_help('s3', ['cp', 'help']))
        self.assertTrue(is_help('s3', ['ls', 's3://photos', 'help']))


class TestLogsPages(BasePagesTest):
    GROUP = LOGS + '#logsV2:log-groups/log-group/%2Faws%2Flambda%2Ff'

    def test_log_group_list(self):
        self.assert_pages(
            [
                ('logs', LOGS + '#logsV2:log-groups'),
                ('logs describe-log-groups', LOGS + '#logsV2:log-groups'),
                ('logs tail', LOGS + '#logsV2:log-groups'),
            ]
        )

    def test_group_and_stream_pages(self):
        self.assert_pages(
            [
                (
                    'logs describe-log-streams '
                    '--log-group-name /aws/lambda/f',
                    self.GROUP,
                ),
                (
                    'logs get-log-events --log-group-name /aws/lambda/f '
                    '--log-stream-name 2026/11/26/s1',
                    self.GROUP + '/log-events/2026%2F11%2F26%2Fs1',
                ),
                (
                    'logs create-log-group --log-group-name app',
                    LOGS + '#logsV2:log-groups/log-group/app',
                ),
            ]
        )

    def test_tail_opens_the_group_it_names(self):
        self.assert_pages(
            [
                ('logs tail /aws/lambda/f', self.GROUP),
                ('logs tail /aws/lambda/f --follow', self.GROUP),
                ('logs tail --follow /aws/lambda/f', self.GROUP),
                ('logs tail /aws/lambda/f --since 1h', self.GROUP),
            ]
        )

    def test_tail_with_an_arn_uses_go_view(self):
        self.assertEqual(
            url_for(f'logs tail {LOG_GROUP_ARN}'),
            go_view(REGION, LOG_GROUP_ARN, 'aws'),
        )


class TestServicePages(BasePagesTest):
    def test_cloudformation(self):
        self.assert_pages(
            [
                ('cloudformation', CLOUDFORMATION),
                ('cloudformation describe-stacks', CLOUDFORMATION + '#stacks'),
                (
                    'cloudformation describe-stacks --stack-name web',
                    CLOUDFORMATION + '#stacks/stackinfo?stackId=web',
                ),
                (
                    'cloudformation create-stack',
                    CLOUDFORMATION + '#stacks/create',
                ),
                ('cloudformation list-exports', CLOUDFORMATION),
            ]
        )

    def test_created_stack_is_opened_after_the_command(self):
        self.assertEqual(
            url_for(
                'cloudformation create-stack --stack-name web',
                {'StackId': 'arn:aws:cloudformation:us-west-2:1:stack/web/1'},
                True,
            ),
            CLOUDFORMATION + '#stacks/stackinfo?stackId=web',
        )

    def test_sqs(self):
        queue = SQS + '#/queues/' + quote_plus(QUEUE)
        self.assert_pages(
            [
                ('sqs', SQS + '#/queues'),
                ('sqs list-queues', SQS + '#/queues'),
                ('sqs create-queue', SQS + '#/create-queue'),
                (f'sqs get-queue-attributes --queue-url {QUEUE}', queue),
            ]
        )
        self.assertEqual(
            url_for(
                'sqs create-queue --queue-name orders',
                {'QueueUrl': QUEUE},
                True,
            ),
            queue,
        )

    def test_lambda(self):
        self.assert_pages(
            [
                ('lambda', LAMBDA + '#/begin'),
                ('lambda list-functions', LAMBDA + '#/functions'),
                ('lambda create-function', LAMBDA + '#/create/function'),
                (
                    'lambda invoke --function-name api out.json',
                    LAMBDA + '#/functions/api',
                ),
                ('lambda list-layers', LAMBDA + '#/begin'),
            ]
        )

    def test_dynamodb(self):
        self.assert_pages(
            [
                ('dynamodb', DYNAMODB),
                ('dynamodb list-tables', DYNAMODB + '#table'),
                ('dynamodb create-table', DYNAMODB + '#create-table'),
                (
                    'dynamodb scan --table-name Music',
                    DYNAMODB + '#table?name=Music',
                ),
            ]
        )

    def test_iam(self):
        self.assert_pages(
            [
                ('iam', IAM),
                ('iam list-roles', IAM + '#/roles'),
                ('iam list-users', IAM + '#/users'),
                (
                    'iam get-user --user-name alice',
                    IAM + '#/users/details/alice',
                ),
                (
                    'iam list-attached-role-policies --role-name Admin',
                    IAM + '#/roles/details/Admin',
                ),
                ('iam list-policies', IAM),
            ]
        )

    def test_several_users_open_the_user_list(self):
        response = {'Users': [{'UserName': 'a'}, {'UserName': 'b'}]}
        self.assertEqual(
            url_for('iam list-users', response, True), IAM + '#/users'
        )
