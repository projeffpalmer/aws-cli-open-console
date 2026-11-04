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
"""Partition hosts and the URL template language."""

import re
import warnings
from urllib.parse import quote, quote_plus

DEFAULT_PARTITION = 'aws'
_HOSTS = {
    'aws': ('console.aws.amazon.com', 'signin.aws.amazon.com'),
    'aws-us-gov': (
        'console.amazonaws-us-gov.com',
        'signin.amazonaws-us-gov.com',
    ),
    'aws-cn': ('console.amazonaws.cn', 'signin.amazonaws.cn'),
}
CONSOLE_HOME_TEMPLATE = 'https://{host}/console/home?region={region}'

_PLACEHOLDER = re.compile(r'\{([^{}:]+)(?::([^{}]*))?\}')
_ENCODERS = {
    'path': lambda value: quote(value, safe=''),
    'query': lambda value: quote_plus(value, safe=''),
    'raw': lambda value: value,
}


def partition_for_region(session, region):
    """Return ``aws``, ``aws-us-gov`` or ``aws-cn`` for ``region``.

    Unknown regions, any lookup error and partitions without a console
    mapping give ``aws``.
    """
    try:
        with warnings.catch_warnings():
            # botocore warns that this component is internal; the CLI
            # itself reads it the same way (customizations.lambdaweb).
            warnings.simplefilter('ignore', DeprecationWarning)
            resolver = session.get_component('endpoint_resolver')
        partition = resolver.get_partition_for_region(region)
    except Exception:
        return DEFAULT_PARTITION
    if partition in _HOSTS:
        return partition
    return DEFAULT_PARTITION


def console_host(partition):
    return _HOSTS.get(partition, _HOSTS[DEFAULT_PARTITION])[0]


def signin_host(partition):
    return _HOSTS.get(partition, _HOSTS[DEFAULT_PARTITION])[1]


def render(template, params):
    """Fill ``{name}`` / ``{name:enc}`` placeholders from ``params``.

    ``enc`` is ``path`` (the default), ``query`` or ``raw``. A
    placeholder whose value is missing or None raises ``KeyError``
    naming it; an unknown encoding raises ``ValueError``.
    """

    def replace(match):
        name, enc = match.group(1), match.group(2)
        if enc is None:
            enc = 'path'
        encoder = _ENCODERS.get(enc)
        if encoder is None:
            raise ValueError(
                f'unknown encoding {enc!r} in placeholder {{{name}:{enc}}}'
            )
        value = params.get(name)
        if value is None:
            raise KeyError(name)
        return encoder(value)

    return _PLACEHOLDER.sub(replace, template)


def console_home(host, region):
    return render(CONSOLE_HOME_TEMPLATE, {'host': host, 'region': region})
