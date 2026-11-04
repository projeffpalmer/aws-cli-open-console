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
"""Intent heuristics: verb, resource type and id options per command.

``derive_intent(node, service_node, resource_types)`` looks only at names:

- the verb class comes from the operation name's first word (``list``,
  ``create`` or ``view``; see ``LIST_VERBS`` and ``CREATE_VERBS``);
  ``batch-get-*`` is a list, ``batch-<verb>-*`` and ``admin-<verb>-*`` drop
  both words from the noun;
- the noun is the rest of the name.  Its last word is singularized and the
  words are joined lowercase without hyphens, then compared with the last
  segment of every CloudFormation type in the service's namespaces
  (``console.namespaces``, first listed namespace preferred).  An equal noun
  is an ``exact`` match; a match after cutting the noun at a preposition
  (``tags-for-resource`` -> ``tags``), after dropping trailing words one at
  a time (``function-configuration`` -> ``function``) or after dropping
  leading qualifiers is ``fuzzy``; otherwise ``none`` and the verb is
  ``home``;
- waiters are views of the noun left after their trailing state words
  (``instance-running`` -> ``instance``, ``stack-create-complete`` ->
  ``stack``);
- ``id_args`` are the options whose values identify the resource, in the
  order given by ``id_args_for``.
"""

import re

QUALITIES = ('exact', 'fuzzy', 'none')

LIST_VERBS = frozenset(
    [
        'list',
        'describe',
        'get',
        'search',
        'query',
        'scan',
        'batch-get',
        'lookup',
    ]
)
CREATE_VERBS = frozenset(
    ['create', 'run', 'register', 'allocate', 'request', 'import', 'launch']
)
# Words that only qualify the verb that follows them (batch-delete-items,
# admin-get-user); the noun starts after that second verb.
VERB_PREFIXES = frozenset(['batch', 'admin'])
# Second words recognised after a verb prefix.
_KNOWN_VERBS = (
    LIST_VERBS
    | CREATE_VERBS
    | frozenset(
        [
            'delete',
            'update',
            'modify',
            'put',
            'tag',
            'untag',
            'start',
            'stop',
            'reboot',
            'terminate',
            'enable',
            'disable',
            'attach',
            'detach',
            'associate',
            'disassociate',
            'add',
            'remove',
            'set',
            'reset',
            'restore',
            'invoke',
            'send',
            'publish',
            'cancel',
            'deregister',
            'release',
            'revoke',
            'authorize',
            'copy',
            'move',
            'rotate',
            'promote',
            'reject',
            'accept',
            'apply',
            'assign',
            'unassign',
            'confirm',
            'respond',
            'initiate',
            'link',
            'unlink',
            'execute',
            'evaluate',
            'write',
            'read',
            'check',
        ]
    )
)
# A preposition ends the noun: list-tags-for-resource -> tags.
PREPOSITIONS = frozenset(
    ['for', 'by', 'from', 'to', 'of', 'in', 'on', 'with', 'at', 'and']
)
# Single words too generic to stand for a resource type in a fuzzy match
# (tag-resource, list-tags-for-resource exist in nearly every service).
GENERIC_NOUNS = frozenset(['resource', 'tag'])
# Verbs whose generic noun (tag-resource) is never a resource type.
TAG_VERBS = frozenset(['tag', 'untag'])
# Trailing waiter words that describe a state, not the resource.
STATE_WORDS = frozenset(
    [
        'active',
        'available',
        'complete',
        'completed',
        'create',
        'created',
        'delete',
        'deleted',
        'deregistered',
        'disabled',
        'done',
        'enabled',
        'exists',
        'failed',
        'import',
        'inactive',
        'not',
        'ok',
        'ready',
        'registered',
        'rollback',
        'running',
        'stable',
        'status',
        'stopped',
        'succeeded',
        'successful',
        'terminated',
        'update',
        'updated',
        'v2',
    ]
)
SINGULAR_EXCEPTIONS = {
    'indices': 'index',
    'aliases': 'alias',
    'analyses': 'analysis',
    'statuses': 'status',
    'addresses': 'address',
    'series': 'series',
    'caches': 'cache',
    'buses': 'bus',
    'data': 'data',
    'metadata': 'metadata',
    'news': 'news',
    'dns': 'dns',
}
ID_SUFFIXES = ('name', 'id', 'arn', 'identifier', 'names', 'ids', 'arns')
GENERIC_ID_OPTIONS = ('name', 'id', 'arn', 'identifier')
EXCLUDED_OPTIONS = frozenset(
    [
        'cli-input-json',
        'cli-input-yaml',
        'generate-cli-skeleton',
        'max-items',
        'max-results',
        'page-size',
        'starting-token',
        'next-token',
        'dry-run',
        'no-dry-run',
        'filters',
        'filter',
        'query',
    ]
)
EXCLUDED_OPTION_SUFFIXES = (
    '-prefix',
    '-pattern',
    '-filter',
    '-filters',
    '-token',
)

_ID_ENDINGS = tuple('-' + suffix for suffix in ID_SUFFIXES)
_NORMALIZE = re.compile(r'[^a-z0-9]')


class TypeIndex:
    """CloudFormation type names indexed by namespace and normalized noun.

    ``lookup(namespaces, key)`` returns the first type, in namespace order,
    whose last segment normalizes to ``key``.
    """

    def __init__(self, resource_types):
        self.by_namespace = {}
        for type_name in sorted(resource_types):
            parts = type_name.split('::')
            if len(parts) != 3:
                continue
            nouns = self.by_namespace.setdefault(parts[1], {})
            nouns.setdefault(normalize(parts[2]), type_name)

    def lookup(self, namespaces, key):
        for ns in namespaces:
            found = self.by_namespace.get(ns, {}).get(key)
            if found:
                return found
        return None


def build_type_index(resource_types):
    if isinstance(resource_types, TypeIndex):
        return resource_types
    return TypeIndex(resource_types)


def normalize(text):
    return _NORMALIZE.sub('', (text or '').lower())


def singularize(word):
    """Singular of one lowercase word, by suffix rules plus exceptions."""
    if word in SINGULAR_EXCEPTIONS:
        return SINGULAR_EXCEPTIONS[word]
    for plural, singular in (
        ('ies', 'y'),
        ('sses', 'ss'),
        ('xes', 'x'),
        ('ches', 'ch'),
        ('shes', 'sh'),
        ('oes', 'o'),
    ):
        if word.endswith(plural) and len(word) > len(plural) + 1:
            return word[: -len(plural)] + singular
    if word.endswith(('ss', 'us', 'sis')) or len(word) <= 2:
        return word
    if word.endswith('s'):
        return word[:-1]
    return word


def split_verb(operation_name):
    """Return ``(verb_class, noun_words)`` for an operation CLI name."""
    words = operation_name.split('-')
    first = words[0]
    if first in VERB_PREFIXES and len(words) > 2 and words[1] in _KNOWN_VERBS:
        phrase = f'{first}-{words[1]}'
        rest = words[2:]
        if phrase in LIST_VERBS:
            return 'list', rest
        return 'view', rest
    if first in VERB_PREFIXES:
        return 'view', words[1:]
    if first in LIST_VERBS:
        return 'list', words[1:]
    if first in CREATE_VERBS:
        return 'create', words[1:]
    return 'view', words[1:]


def waiter_noun(waiter_name):
    """Noun words of a waiter name without its trailing state words."""
    words = waiter_name.split('-')
    while len(words) > 1:
        if words[-2:] == ['in', 'service'] and len(words) > 2:
            words = words[:-2]
        elif words[-1] in STATE_WORDS:
            words = words[:-1]
        else:
            break
    return words


def candidates(words):
    """Yield ``(noun_words, quality)`` in the order they are tried.

    First the whole noun (``exact``).  Then, as ``fuzzy``, the words before
    the first preposition with trailing words dropped one at a time, then
    with leading qualifiers dropped; then the same for the words after each
    preposition (``add-tags-to-certificate`` -> ``certificate``).  A fuzzy
    candidate never contains a preposition and is never a lone word of
    ``GENERIC_NOUNS``.
    """
    if not words:
        return
    yield words, 'exact'
    seen = {tuple(words)}
    for segment in _segments(words):
        for start in range(len(segment)):
            for end in range(len(segment), start, -1):
                part = segment[start:end]
                if tuple(part) in seen:
                    continue
                seen.add(tuple(part))
                if _generic(part):
                    continue
                yield part, 'fuzzy'


def match_noun(words, namespaces, index):
    """Return ``(resource_type, noun_words, quality)``; quality 'none'."""
    for part, quality in candidates(words):
        singular = part[:-1] + [singularize(part[-1])]
        for form in (singular, part):
            found = index.lookup(namespaces, normalize(''.join(form)))
            if found:
                return found, singular, quality
    return None, None, 'none'


def id_args_for(args, noun_words):
    """Option names (with ``--``) that identify the resource, in order.

    ``args`` is a node's ``_args`` map; ``noun_words`` the matched noun.
    """
    options = [
        name
        for name, info in (args or {}).items()
        if not info.get('positional') and not _excluded(name)
    ]
    noun = '-'.join(noun_words or [])
    found = []

    def add(name):
        if name not in found:
            found.append(name)

    if noun:
        for name in options:
            head, _, suffix = name.rpartition('-')
            if suffix in ID_SUFFIXES and _same_noun(head, noun):
                add(name)
    for generic in GENERIC_ID_OPTIONS:
        if generic in options:
            add(generic)
    if noun:
        for name in options:
            if args[name].get('list') and name != noun:
                if _same_noun(name, noun):
                    add(name)
    for name in options:
        if args[name].get('required') and name.endswith(_ID_ENDINGS):
            add(name)
    return ['--' + name for name in found]


def derive_intent(node, service_node, resource_types):
    """Return ``(intent, quality)`` for an operation or waiter node.

    ``resource_types`` is the list of CloudFormation type names or a
    ``TypeIndex`` built from it.  ``quality`` is one of ``QUALITIES``.
    Other node kinds return ``(None, None)``.
    """
    kind = node.get('kind')
    if kind == 'operation':
        verb, words = split_verb(node['name'])
        if node['name'].split('-')[0] in TAG_VERBS and _generic(words):
            # tag-resource / untag-resource name no resource type.
            words = []
    elif kind == 'waiter':
        verb, words = 'view', waiter_noun(node['name'])
    else:
        return None, None
    console = (service_node or {}).get('console') or {}
    namespaces = console.get('namespaces') or []
    resource_type, noun, quality = None, None, 'none'
    if namespaces and words:
        index = build_type_index(resource_types)
        resource_type, noun, quality = match_noun(words, namespaces, index)
    if resource_type is None:
        return {'verb': 'home', 'resource_type': None, 'id_args': []}, 'none'
    intent = {
        'verb': verb,
        'resource_type': resource_type,
        'id_args': id_args_for(node.get('_args'), noun),
    }
    return intent, quality


def _generic(words):
    return len(words) == 1 and singularize(words[0]) in GENERIC_NOUNS


def _segments(words):
    """Runs of ``words`` between prepositions, in order."""
    segment = []
    for word in words:
        if word in PREPOSITIONS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(word)
    if segment:
        yield segment


def _same_noun(head, noun):
    if head == noun:
        return True
    words = head.split('-')
    return '-'.join(words[:-1] + [singularize(words[-1])]) == noun


def _excluded(name):
    return name in EXCLUDED_OPTIONS or name.endswith(EXCLUDED_OPTION_SUFFIXES)
