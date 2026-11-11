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
"""Resolve a command that ran to the page of the resource it acted on.

Used by ``--open-console``. The identifiers come from the API response
(``TableName`` of ``dynamodb create-table``, every ``InstanceId`` of
``ec2 run-instances``) and, when the response has none, from the typed
arguments. They are handed to the page of the command itself when it can
show one resource, else to the sibling command with the same resource type
that can (``describe-table``, ``describe-instances``), and rendered by
``resolver.resolve`` exactly as ``--console-link`` would render them.
"""

import logging

from botocore import xform_name

from awscli.customizations.open_the_console_to_this import args, db, resolver

LOG = logging.getLogger(__name__)

VIEW_PREFIXES = ('describe-', 'get-', 'head-')
SKIPPED_KEYS = frozenset(['ResponseMetadata'])


def resolve_after_run(root, command, remaining, response, ctx):
    """Return the :class:`resolver.Decision` for a command that ran.

    ``response`` is the parsed API response, a list of pages, or None
    when the command made no API call this module could see. Never raises
    for user input or response content.
    """
    tokens = [command] + list(remaining or ())
    try:
        node, consumed, rest = db.find_node(root, tokens)
        if consumed >= 2:
            decision = _from_resource(
                root, tokens[:consumed], node, rest, response, ctx
            )
            if decision is not None:
                return decision
    except Exception:
        LOG.debug(
            'Following the response of %r failed', tokens, exc_info=True
        )
    return resolver.resolve(root, command, remaining, ctx)


def _from_resource(root, path_tokens, node, rest, response, ctx):
    parent, _, _ = db.find_node(root, path_tokens[:-1])
    typed = args.parse_remaining(
        rest,
        node.get('positional') or [],
        flags=node.get('flags', ()),
        scalars=node.get('scalars', ()),
    )
    candidates = view_candidates(node, parent)
    values_by_name = {}
    for candidate in candidates:
        arg_tokens = _arg_tokens(candidate, response, typed, values_by_name)
        if not arg_tokens:
            continue
        decision = _resolve_candidate(root, candidate, arg_tokens, ctx)
        if decision.params:
            LOG.debug(
                'Console: %s follows %s with %r',
                node.get('path'),
                candidate.get('path'),
                arg_tokens,
            )
            return decision
    if _verb(node) == 'create' and candidates:
        # Nothing identified the new resource: its list page, not the
        # create wizard of a resource that now exists.
        return _resolve_candidate(root, candidates[0], [], ctx)
    return None


def _verb(node):
    return (node.get('intent') or {}).get('verb')


def _resource_type(node):
    return (node.get('intent') or {}).get('resource_type')


def _shows_one(node):
    url = node.get('url') or {}
    return bool(url.get('with_id') or url.get('variants'))


def _canonical_names(resource_type):
    noun = xform_name(resource_type.rsplit('::', 1)[-1], '-')
    return frozenset(
        prefix + noun + plural
        for prefix in VIEW_PREFIXES
        for plural in ('', 's')
    )


def _rank(node, canonical):
    name = node.get('name') or ''
    return (
        name not in canonical,
        not name.startswith(VIEW_PREFIXES),
        _verb(node) not in ('view', 'list'),
        len(name),
        name,
    )


def view_candidates(node, parent):
    """Nodes whose page can show the resource ``node`` acted on, in order.

    The node itself first when it can show one resource, then its siblings
    with the same resource type that can: the resource's own
    ``describe-<noun>``, ``get-<noun>`` or ``head-<noun>`` first, then other
    ``describe-``, ``get-`` and ``head-`` commands, then ``view`` and
    ``list`` verbs, shorter names first.
    """
    out = [node] if _shows_one(node) else []
    resource_type = _resource_type(node)
    if resource_type:
        canonical = _canonical_names(resource_type)
        siblings = [
            child
            for child in (parent.get('children') or {}).values()
            if child is not node
            and _resource_type(child) == resource_type
            and _shows_one(child)
        ]
        out.extend(sorted(siblings, key=lambda c: _rank(c, canonical)))
    return out


def _arg_names(node):
    """Option names (without dashes) that feed the node's templates."""
    intent = node.get('intent') or {}
    positional = set(node.get('positional') or ())
    names = [arg.lstrip('-') for arg in intent.get('id_args') or ()]
    for name, spec in sorted((intent.get('params') or {}).items()):
        arg = (spec or {}).get('arg') or name
        if arg not in positional:
            names.append(arg.lstrip('-'))
    return list(dict.fromkeys(names))


def _resolve_candidate(root, candidate, extra_tokens, ctx):
    parts = candidate['path'].split('.')[1:]
    return resolver.resolve(root, parts[0], parts[1:] + extra_tokens, ctx)


def _arg_tokens(node, response, typed, values_by_name):
    """Arguments for ``node``: response values, else typed ones.

    Typed positionals (the ``s3://bucket`` of ``s3 mb``) are passed after
    ``--`` to a node that takes positionals. ``values_by_name`` caches
    response lookups for one ``_from_resource`` call; sibling candidates
    mostly ask for the same names.
    """
    tokens = []
    for name in _arg_names(node):
        if name not in values_by_name:
            values_by_name[name] = find_values(response, name)
        values = values_by_name[name] or typed.options.get(name)
        values = [v for v in values or () if not v.startswith('--')]
        if values:
            tokens.append('--' + name)
            tokens.extend(values)
    if node.get('positional') and typed.positionals:
        tokens.append('--')
        tokens.extend(typed.positionals)
    return tokens


def _normalize(name):
    return name.replace('-', '').replace('_', '').lower()


def find_values(response, option_name):
    """String values of the response key that matches ``option_name``.

    ``table-name`` matches ``TableName`` and ``db-instance-identifier``
    matches ``DBInstanceIdentifier`` (case and dashes are ignored); a
    plural name such as ``instance-ids`` also matches ``InstanceId``. The
    shallowest depth with a match wins and every value there is returned
    in order without repeats; lists do not add depth, so the ``InstanceId``
    of every instance in ``Instances`` is found together.
    """
    if response is None:
        return []
    wanted = _normalize(option_name)
    keys = [wanted]
    if wanted.endswith('s'):
        keys.append(wanted[:-1])
    for key in keys:
        values = _search(response, key)
        if values:
            return values
    return []


def _search(response, key):
    level = [response]
    while level:
        found = []
        deeper = []
        for item in _flatten(level):
            for name, value in item.items():
                if name in SKIPPED_KEYS:
                    continue
                if _normalize(name) == key:
                    found.extend(_strings(value))
                elif isinstance(value, (dict, list)):
                    deeper.append(value)
        if found:
            return list(dict.fromkeys(found))
        level = deeper
    return []


def _flatten(items):
    """Yield the dicts of ``items``, descending into lists."""
    stack = list(reversed(items))
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            stack.extend(reversed(item))


def _strings(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    return []
