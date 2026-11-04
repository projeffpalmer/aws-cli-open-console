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
import warnings

from botocore.exceptions import UnknownRegionError

from awscli.customizations.open_the_console_to_this import urls
from awscli.testutils import mock, unittest


def session_with_partition(partition=None, error=None):
    resolver = mock.Mock()
    if error is not None:
        resolver.get_partition_for_region.side_effect = error
    else:
        resolver.get_partition_for_region.return_value = partition
    session = mock.Mock()
    session.get_component.return_value = resolver
    return session, resolver


class TestPartitionForRegion(unittest.TestCase):
    def test_uses_the_endpoint_resolver(self):
        session, resolver = session_with_partition('aws-us-gov')
        result = urls.partition_for_region(session, 'us-gov-west-1')
        self.assertEqual(result, 'aws-us-gov')
        session.get_component.assert_called_once_with('endpoint_resolver')
        resolver.get_partition_for_region.assert_called_once_with(
            'us-gov-west-1'
        )

    def test_known_partitions(self):
        for partition in ('aws', 'aws-us-gov', 'aws-cn'):
            session, _ = session_with_partition(partition)
            self.assertEqual(
                urls.partition_for_region(session, 'r'), partition
            )

    def test_unknown_region_is_aws(self):
        error = UnknownRegionError(region_name='xx-nowhere-1', error_msg='x')
        session, _ = session_with_partition(error=error)
        self.assertEqual(urls.partition_for_region(session, 'xx'), 'aws')

    def test_any_error_is_aws(self):
        session = mock.Mock()
        session.get_component.side_effect = RuntimeError('boom')
        self.assertEqual(urls.partition_for_region(session, 'r'), 'aws')

    def test_deprecation_warning_is_not_an_error(self):
        session = mock.Mock()

        def get_component(name):
            warnings.warn('internal component', DeprecationWarning)
            resolver = mock.Mock()
            resolver.get_partition_for_region.return_value = 'aws-cn'
            return resolver

        session.get_component.side_effect = get_component
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            result = urls.partition_for_region(session, 'cn-north-1')
        self.assertEqual(result, 'aws-cn')

    def test_partition_without_console_is_aws(self):
        session, _ = session_with_partition('aws-iso')
        self.assertEqual(urls.partition_for_region(session, 'r'), 'aws')

    def test_real_session(self):
        from awscli.testutils import create_clidriver

        session = create_clidriver().session
        cases = {
            'us-west-2': 'aws',
            'us-gov-west-1': 'aws-us-gov',
            'cn-north-1': 'aws-cn',
        }
        for region, expected in cases.items():
            self.assertEqual(
                urls.partition_for_region(session, region), expected
            )
        self.assertEqual(urls.partition_for_region(session, None), 'aws')


class TestHosts(unittest.TestCase):
    def test_console_hosts(self):
        self.assertEqual(urls.console_host('aws'), 'console.aws.amazon.com')
        self.assertEqual(
            urls.console_host('aws-us-gov'), 'console.amazonaws-us-gov.com'
        )
        self.assertEqual(urls.console_host('aws-cn'), 'console.amazonaws.cn')
        self.assertEqual(
            urls.console_host('aws-iso-b'), 'console.aws.amazon.com'
        )

    def test_signin_hosts(self):
        self.assertEqual(urls.signin_host('aws'), 'signin.aws.amazon.com')
        self.assertEqual(
            urls.signin_host('aws-us-gov'), 'signin.amazonaws-us-gov.com'
        )
        self.assertEqual(urls.signin_host('aws-cn'), 'signin.amazonaws.cn')
        self.assertEqual(urls.signin_host('other'), 'signin.aws.amazon.com')


class TestRender(unittest.TestCase):
    def test_no_placeholders(self):
        self.assertEqual(urls.render('https://x/y', {}), 'https://x/y')

    def test_regional_template(self):
        result = urls.render(
            'https://{region}.{host}/ec2/home?region={region}#Instances:',
            {'region': 'us-west-2', 'host': 'console.aws.amazon.com'},
        )
        self.assertEqual(
            result,
            'https://us-west-2.console.aws.amazon.com/ec2/home'
            '?region=us-west-2#Instances:',
        )

    def test_default_is_path_encoding(self):
        result = urls.render('/{name}', {'name': '/aws/lambda/f n+1'})
        self.assertEqual(result, '/%2Faws%2Flambda%2Ff%20n%2B1')

    def test_explicit_path_encoding(self):
        result = urls.render('/{name:path}', {'name': 'a/b c'})
        self.assertEqual(result, '/a%2Fb%20c')

    def test_query_encoding(self):
        result = urls.render('?p={prefix:query}', {'prefix': '2026/a b+c'})
        self.assertEqual(result, '?p=2026%2Fa+b%2Bc')

    def test_raw(self):
        arn = 'arn:aws:sns:us-east-1:123456789012:topic/a b'
        self.assertEqual(urls.render('#{id:raw}', {'id': arn}), '#' + arn)

    def test_unicode_value(self):
        self.assertEqual(urls.render('{n}', {'n': 'café'}), 'caf%C3%A9')

    def test_unreserved_characters_kept(self):
        self.assertEqual(urls.render('{n}', {'n': 'a-b_c.d~e'}), 'a-b_c.d~e')

    def test_same_name_twice_with_different_encodings(self):
        result = urls.render('{v}|{v:query}|{v:raw}', {'v': 'a b/c'})
        self.assertEqual(result, 'a%20b%2Fc|a+b%2Fc|a b/c')

    def test_extra_params_ignored(self):
        self.assertEqual(urls.render('{a}', {'a': '1', 'b': '2'}), '1')

    def test_missing_name_raises_key_error_naming_it(self):
        with self.assertRaises(KeyError) as context:
            urls.render('https://{host}/{bucket:path}', {'host': 'h'})
        self.assertEqual(context.exception.args, ('bucket',))

    def test_none_value_is_missing(self):
        with self.assertRaises(KeyError) as context:
            urls.render('{prefix:query}', {'prefix': None})
        self.assertEqual(context.exception.args, ('prefix',))

    def test_unknown_encoding_raises_value_error(self):
        with self.assertRaises(ValueError):
            urls.render('{a:base64}', {'a': 'x'})

    def test_does_not_modify_params(self):
        params = {'a': 'x y'}
        urls.render('{a}', params)
        self.assertEqual(params, {'a': 'x y'})


class TestConsoleHome(unittest.TestCase):
    def test_console_home(self):
        self.assertEqual(
            urls.console_home('console.aws.amazon.com', 'eu-west-1'),
            'https://console.aws.amazon.com/console/home?region=eu-west-1',
        )

    def test_console_home_gov(self):
        self.assertEqual(
            urls.console_home('console.amazonaws-us-gov.com', 'us-gov-west-1'),
            'https://console.amazonaws-us-gov.com/console/home'
            '?region=us-gov-west-1',
        )
