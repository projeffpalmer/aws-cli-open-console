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

DOCS_HOME = 'https://docs.aws.amazon.com/'
TOPIC_URL = 'https://docs.aws.amazon.com/cli/latest/topic/{}.html'
TOPICS_INDEX = 'index'


def docs_url(root, node, tokens_after_node):
    """Return the documentation URL for ``node``.

    At the root, ``help`` (or nothing) gives ``DOCS_HOME`` and
    ``help <topic>`` gives the CLI topic page (``topics`` gives the
    topic index). Every other node gives ``node['docs']['best']``.
    """
    tokens = list(tokens_after_node or ())
    if node is root:
        if len(tokens) == 2 and tokens[0] == 'help':
            topic = tokens[1]
            if topic == 'topics':
                topic = TOPICS_INDEX
            return TOPIC_URL.format(quote(topic, safe=''))
        if not tokens or tokens == ['help']:
            return DOCS_HOME
    return node['docs']['best']
