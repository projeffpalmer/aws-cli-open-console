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

from console_db import validate  # noqa: E402

WITHOUT = '302 to the same path without a trailing slash'
WITH = '302 to the same path with a trailing slash'


@pytest.mark.parametrize(
    'url,location',
    [
        (
            'https://console.aws.amazon.com/license-manager/',
            'https://console.aws.amazon.com/license-manager',
        ),
        (
            'https://us-west-2.console.aws.amazon.com'
            '/codesuite/settings/connections/',
            'https://us-west-2.console.aws.amazon.com'
            '/codesuite/settings/connections',
        ),
        (
            'https://us-west-2.console.aws.amazon.com'
            '/rolesanywhere/home/?region=us-west-2',
            'https://us-west-2.console.aws.amazon.com'
            '/rolesanywhere/home?region=us-west-2',
        ),
        (
            'https://us-west-2.console.aws.amazon.com'
            '/systems-manager/parameters/?region=us-west-2&tab=Table',
            'https://us-west-2.console.aws.amazon.com'
            '/systems-manager/parameters?region=us-west-2&tab=Table',
        ),
    ],
)
def test_302_dropping_one_trailing_slash_passes(url, location):
    assert validate.classify_response(url, 302, location) == (
        validate.PASS,
        WITHOUT,
    )


def test_302_adding_one_trailing_slash_passes():
    assert validate.classify_response(
        'https://console.aws.amazon.com/license-manager',
        '302',
        'https://console.aws.amazon.com/license-manager/',
    ) == (validate.PASS, WITH)


def test_relative_location_dropping_the_slash_passes():
    assert validate.classify_response(
        'https://us-west-2.console.aws.amazon.com/rolesanywhere/home/'
        '?region=us-west-2',
        302,
        '/rolesanywhere/home?region=us-west-2',
    ) == (validate.PASS, WITHOUT)


@pytest.mark.parametrize(
    'url,location',
    [
        # A different path.
        (
            'https://us-west-2.console.aws.amazon.com/datapipeline/',
            'https://us-west-2.console.aws.amazon.com/console/home',
        ),
        # Same path without the slash, but the query changed.
        (
            'https://us-west-2.console.aws.amazon.com'
            '/rolesanywhere/home/?region=us-west-2',
            'https://us-west-2.console.aws.amazon.com/rolesanywhere/home',
        ),
        # Same path without the slash, but another host.
        (
            'https://console.aws.amazon.com/license-manager/',
            'https://example.com/license-manager',
        ),
        # More than one trailing slash removed.
        (
            'https://console.aws.amazon.com/license-manager//',
            'https://console.aws.amazon.com/license-manager',
        ),
        # Scheme changed.
        (
            'https://console.aws.amazon.com/license-manager/',
            'http://console.aws.amazon.com/license-manager',
        ),
    ],
)
def test_302_to_another_page_fails(url, location):
    assert validate.classify_response(url, 302, location) == (
        validate.FAIL,
        '302 to another page',
    )


def test_302_to_same_path_on_another_console_host_passes():
    assert validate.classify_response(
        'https://console.aws.amazon.com/wafv2/homev2/web-acls',
        302,
        'https://us-east-1.console.aws.amazon.com/wafv2/homev2/web-acls',
    ) == (validate.PASS, '302 to the same path on another console host')


def test_302_to_sign_in_passes():
    assert validate.classify_response(
        'https://us-west-2.console.aws.amazon.com/ec2/home',
        302,
        'https://signin.aws.amazon.com/oauth?redirect_uri=x',
    ) == (validate.PASS, '302 to sign-in')


def test_go_redirect_to_a_console_host_passes():
    assert validate.classify_response(
        'https://console.aws.amazon.com/go/view?service=ec2',
        302,
        'https://us-west-2.console.aws.amazon.com/ec2/home',
    ) == (validate.PASS, '/go/ redirect to a console host')


@pytest.mark.parametrize(
    'status,location,expected',
    [
        (200, '', (validate.PASS, '200')),
        (404, '', (validate.FAIL, 'status 404')),
        ('000', 'timed out', (validate.FAIL, 'unreachable: timed out')),
    ],
)
def test_status_verdicts(status, location, expected):
    url = 'https://us-west-2.console.aws.amazon.com/datapipeline/'
    assert validate.classify_response(url, status, location) == expected
