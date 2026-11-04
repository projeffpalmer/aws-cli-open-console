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
"""Load the console URL database and look up command nodes."""

import json
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data',
    'open_the_console_to_this',
    'commands.json',
)
SCHEMA_VERSION = 1

_CACHE = {}


def load_db():
    """Return the parsed database, reading ``DB_PATH`` once.

    The cache is keyed by path, so patching ``DB_PATH`` loads the new
    file. Errors (``OSError``, ``ValueError``) propagate to the caller.
    """
    path = DB_PATH
    if path not in _CACHE:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(
            data.get('root'), dict
        ):
            raise ValueError('the database has no root node')
        if data.get('schema') != SCHEMA_VERSION:
            raise ValueError(
                f'unsupported schema version {data.get("schema")!r}'
            )
        _CACHE.clear()
        _CACHE[path] = data
    return _CACHE[path]


def reset_cache():
    """Forget the loaded database (for tests)."""
    _CACHE.clear()


def find_node(root, tokens):
    """Walk ``root`` by consecutive child names.

    Stops at the first token that is not a child name, starts with
    ``-`` or equals ``help``. Returns ``(node, consumed, rest)``.
    """
    tokens = list(tokens)
    node = root
    consumed = 0
    for token in tokens:
        if token.startswith('-') or token == 'help':
            break
        child = (node.get('children') or {}).get(token)
        if child is None:
            break
        node = child
        consumed += 1
    return node, consumed, tokens[consumed:]
