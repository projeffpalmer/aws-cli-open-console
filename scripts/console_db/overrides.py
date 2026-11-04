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
"""Hand edits: ``scripts/console_db/overrides/*.yaml``.

Every file except ``services.yaml`` and ``docs.yaml`` (keyed by tier-1 name
and read by ``services.py`` and ``docs.py``) is keyed by node path
(``aws.s3.ls``).  Each value may set ``intent``, ``url``, ``docs`` and
``title``; an override replaces that object on the node whole, with no deep
merge.  A path that is not in the command tree, a path set by two files, or
an unknown field stops the build with a message naming the key.
"""

import copy
import os

from ruamel.yaml import YAML

TIER1_FILES = frozenset(['services.yaml', 'docs.yaml'])
OVERRIDE_FIELDS = ('intent', 'url', 'docs', 'title')


class BuildError(Exception):
    """The inputs cannot produce a valid database; the message says why."""


def load_yaml(path):
    """Load one YAML file into plain dicts and lists (``{}`` when empty)."""
    yaml = YAML(typ='safe', pure=True)
    with open(path, encoding='utf-8') as f:
        data = yaml.load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BuildError(f'{path}: the top level must be a mapping')
    return data


def load_tier1_file(directory, filename):
    """Load ``services.yaml`` or ``docs.yaml``; missing file -> ``{}``."""
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return {}
    return load_yaml(path)


def load_overrides(directory):
    """Return ``{node_path: {field: value}}`` from every path-keyed file."""
    overrides = {}
    origin = {}
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith('.yaml') or filename in TIER1_FILES:
            continue
        path = os.path.join(directory, filename)
        for key, value in load_yaml(path).items():
            where = f'{filename}: {key}'
            if not isinstance(key, str) or not key.startswith('aws'):
                raise BuildError(f'{where}: keys must be node paths (aws.x.y)')
            if key in overrides:
                raise BuildError(
                    f'{where}: already overridden in {origin[key]}'
                )
            if not isinstance(value, dict):
                raise BuildError(f'{where}: expected a mapping')
            unknown = sorted(set(value) - set(OVERRIDE_FIELDS))
            if unknown:
                raise BuildError(
                    f'{where}: unknown fields {unknown}; allowed: '
                    f'{list(OVERRIDE_FIELDS)}'
                )
            overrides[key] = value
            origin[key] = filename
    return overrides


def apply_overrides(root, overrides):
    """Replace ``intent``/``url``/``docs``/``title`` on the named nodes."""
    by_path = {}
    stack = [root]
    while stack:
        node = stack.pop()
        by_path[node['path']] = node
        stack.extend((node.get('children') or {}).values())
    for key in sorted(overrides):
        node = by_path.get(key)
        if node is None:
            raise BuildError(
                f'override {key!r} names a path that is not in the command '
                'tree'
            )
        for field in OVERRIDE_FIELDS:
            if field in overrides[key]:
                node[field] = copy.deepcopy(overrides[key][field])
