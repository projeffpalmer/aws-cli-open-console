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
"""Documentation URLs for ``aws ... help --console-link``."""

from urllib.parse import quote

from awscli.customizations.openconsole.resolver import (
    operation_known,
    parse_command,
)

DOCS_HOME = 'https://docs.aws.amazon.com/'
TOPIC_URL = 'https://docs.aws.amazon.com/cli/latest/topic/{}.html'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'
TOPICS_INDEX = 'index'
# Services whose documentation landing page is
# ``docs.aws.amazon.com/<name>/``. Any other command uses its AWS CLI
# reference, which always exists.
_GUIDE_SERVICES = frozenset(
    [
        'apigateway',
        'cloudformation',
        'dynamodb',
        'ec2',
        'ecs',
        'events',
        'iam',
        'lambda',
        'rds',
        's3',
        'sns',
        'sqs',
    ]
)


def docs_url(command, remaining, session=None):
    """Return the documentation URL for a help command."""
    kind, service, parts = _target(command, remaining, session)
    if kind == 'home':
        return DOCS_HOME
    if kind == 'topic':
        return TOPIC_URL.format(quote(parts[0], safe=''))
    if kind == 'service':
        return f'https://docs.aws.amazon.com/{quote(service, safe="")}/'
    path = '/'.join(quote(part, safe='') for part in parts)
    return f'{REFERENCE}{quote(service, safe="")}/{path}.html'


def _target(command, remaining, session):
    remaining = list(remaining or ())
    if command == 'help':
        if len(remaining) == 1:
            topic = remaining[0]
            if topic == 'topics':
                topic = TOPICS_INDEX
            return 'topic', None, (topic,)
        return 'home', None, ()
    parsed = parse_command(command, remaining, session)
    if not parsed.operation:
        return _service_target(command)
    if parsed.operation == 'wait' and not parsed.positionals:
        return 'reference', command, ('wait', 'index')
    if not operation_known(session, command, parsed.operation):
        return _service_target(command)
    parts = [parsed.operation]
    if parsed.operation == 'wait' and parsed.positionals:
        parts.append(parsed.positionals[0])
    return 'reference', command, tuple(parts)


def _service_target(service):
    """The landing page of ``service``, else its AWS CLI reference."""
    if service in _GUIDE_SERVICES:
        return 'service', service, ()
    return 'reference', service, ('index',)
