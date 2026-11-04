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
"""Walk the CLI command tree into the skeleton of the console database.

The walk is the one ``awscli/autocomplete/local/indexer.py`` does: the
driver's ``subcommand_table``, then each command's ``subcommand_table`` and
``arg_table``.  Every node gets ``name``, ``path``, ``tier``, ``kind`` and,
where known, ``title`` and ``positional``; a node with positional args also
gets ``flags`` (options that take no value) and ``scalars`` (options that
take exactly one value), both sorted, so the runtime tokenizer can tell a
positional from an option value.  Two private keys support later pipeline
steps and are removed by ``export``:

``_args``
    ``{cli_name: {"required": bool, "list": bool, "positional": bool,
    "boolean": bool}}`` in arg table order.  ``positional`` also covers
    streaming ``outfile`` arguments, whose ``positional_arg`` is False
    although argparse takes them positionally.  ``boolean`` means the option
    takes no value: its argparse action is ``store_true``/``store_false``
    (custom flags, model booleans and their ``--no-`` twins, EC2's negative
    boolean parameters) or another valueless action.  The type name alone
    is not enough: flattened boolean members (``cloudsearch``) take
    ``true``/``false`` as a value.
``_meta``
    model facts: ``service_name``, ``service_id``, ``endpoint_prefix`` and
    ``signing_name`` on services, ``operation`` on API operations.
"""

import re

from awscli.autocomplete.local.indexer import ModelIndexer
from awscli.clidriver import ServiceOperation

ROOT_NAME = 'aws'
EXCLUDED_NAMES = frozenset(['help'])

# argparse actions that consume no value.
_VALUELESS_ACTIONS = frozenset(
    ['store_true', 'store_false', 'store_const', 'count', 'help', 'version']
)
_RST_LITERAL = re.compile(r'``([^`]*)``')
_RST_ROLE = re.compile(r':[a-z]+:`([^`<]*)(?:<[^>]*>)?`')


def walk_command_tree(driver):
    """Return the root node of ``driver``'s command tree."""
    root = _new_node(ROOT_NAME, ROOT_NAME, 0, 'root')
    root['_args'] = _arg_map(driver.arg_table)
    help_table = driver.create_help_command().command_table
    for name in sorted(driver.subcommand_table):
        if name in EXCLUDED_NAMES:
            continue
        command = driver.subcommand_table[name]
        node = _walk_service(name, command, help_table.get(name))
        root['children'][name] = node
    return root


def iter_nodes(node):
    """Yield ``node`` and its descendants depth first, children by name."""
    yield node
    children = node.get('children') or {}
    for name in sorted(children):
        yield from iter_nodes(children[name])


def tier1_nodes(root):
    """Return ``[(name, node)]`` for the tier-1 children, sorted by name."""
    children = root.get('children') or {}
    return [(name, children[name]) for name in sorted(children)]


def _walk_service(name, command, help_command):
    service_model = getattr(help_command, 'service_model', None)
    path = f'{ROOT_NAME}.{name}'
    if service_model is not None:
        node = _new_node(name, path, 1, 'service')
        metadata = service_model.metadata
        node['title'] = metadata.get('serviceFullName')
        node['_meta'] = {
            'service_name': service_model.service_name,
            'service_id': metadata.get('serviceId'),
            'endpoint_prefix': metadata.get('endpointPrefix'),
            'signing_name': metadata.get('signingName'),
        }
    else:
        node = _new_node(name, path, 1, 'custom')
        high_level = ModelIndexer._HIGH_LEVEL_SERVICE_FULL_NAMES
        node['title'] = high_level.get(name) or _custom_title(command)
    _fill_args(node, command.arg_table)
    _walk_children(node, command.subcommand_table)
    return node


def _walk_children(parent, subcommand_table):
    tier = parent['tier'] + 1
    for name in sorted(subcommand_table):
        if name in EXCLUDED_NAMES:
            continue
        command = subcommand_table[name]
        path = f'{parent["path"]}.{name}'
        children_table = command.subcommand_table
        if tier >= 3:
            kind = 'waiter'
        elif isinstance(command, ServiceOperation):
            kind = 'operation'
        elif children_table:
            kind = 'group'
        else:
            kind = 'subcommand'
        node = _new_node(name, path, tier, kind)
        if isinstance(command, ServiceOperation):
            node['_meta'] = {'operation': command._operation_model.name}
        _fill_args(node, command.arg_table)
        if children_table:
            _walk_children(node, children_table)
        parent['children'][name] = node


def _new_node(name, path, tier, kind):
    return {
        'name': name,
        'path': path,
        'tier': tier,
        'kind': kind,
        'title': None,
        'children': {},
    }


def _fill_args(node, arg_table):
    args = _arg_map(arg_table)
    node['_args'] = args
    positional = [name for name, info in args.items() if info['positional']]
    if positional:
        node['positional'] = positional
        node['flags'] = sorted(
            name
            for name, info in args.items()
            if info['boolean'] and not info['positional']
        )
        node['scalars'] = sorted(
            name
            for name, info in args.items()
            if not (info['boolean'] or info['list'] or info['positional'])
        )


def _arg_map(arg_table):
    args = {}
    for name, arg in arg_table.items():
        nargs = arg.nargs
        is_list = (
            arg.cli_type_name == 'list'
            or nargs in ('*', '+')
            or (isinstance(nargs, int) and nargs > 1)
        )
        args[name] = {
            'required': bool(arg.required),
            'list': bool(is_list),
            'positional': _is_positional(arg),
            'boolean': _is_valueless(arg),
        }
    return args


def _is_positional(arg):
    # StreamingOutputArgument (the ``outfile`` of ``lambda invoke``,
    # ``s3api get-object`` and 59 more operations) reports
    # ``positional_arg`` False but registers its bare name with argparse,
    # which makes it positional; the cli_name has no leading ``--`` then.
    return bool(arg.positional_arg) or not arg.cli_name.startswith('--')


def _is_valueless(arg):
    action = getattr(arg, '_action', None)
    return (isinstance(action, str) and action in _VALUELESS_ACTIONS) or (
        arg.nargs == 0
    )


def _custom_title(command):
    """First sentence of a custom command's description, plain text."""
    help_command = command.create_help_command()
    text = getattr(help_command, 'description', None)
    if not isinstance(text, str):
        return None
    paragraph = text.strip().split('\n\n')[0]
    paragraph = _RST_ROLE.sub(r'\1', _RST_LITERAL.sub(r'\1', paragraph))
    paragraph = ' '.join(paragraph.split())
    match = re.match(r'(.+?\.)(\s|$)', paragraph)
    return match.group(1) if match else (paragraph or None)
