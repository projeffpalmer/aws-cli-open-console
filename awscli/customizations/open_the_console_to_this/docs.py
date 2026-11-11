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
"""Documentation URLs for ``aws ... help --console-link``."""

from urllib.parse import quote

from awscli.customizations.open_the_console_to_this.resolver import (
    operation_known,
    parse_command,
)

DOCS_HOME = 'https://docs.aws.amazon.com/'
TOPIC_URL = 'https://docs.aws.amazon.com/cli/latest/topic/{}.html'
REFERENCE = 'https://docs.aws.amazon.com/cli/latest/reference/'
TOPICS_INDEX = 'index'
_GUIDE_SERVICES = frozenset(['s3'])
_REFERENCE_ONLY = frozenset(['configure', 'history'])


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
        if _service_guide(session, command):
            return 'service', command, ()
        return 'reference', command, ('index',)
    if parsed.operation == 'wait' and not parsed.positionals:
        return 'reference', command, ('wait', 'index')
    if not operation_known(session, command, parsed.operation):
        return 'service', command, ()
    parts = [parsed.operation]
    if parsed.operation == 'wait' and parsed.positionals:
        parts.append(parsed.positionals[0])
    return 'reference', command, tuple(parts)


def _service_guide(session, service):
    """True when ``service`` has a documentation landing page."""
    if service in _GUIDE_SERVICES:
        return True
    if service in _REFERENCE_ONLY:
        return False
    if session is None or not hasattr(session, 'get_available_services'):
        return True
    try:
        names = session.get_available_services()
    except Exception:
        return True
    return service in names
