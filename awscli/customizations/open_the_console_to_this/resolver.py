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
"""Resolve a typed CLI command to a console URL (contract section 4).

``resolve(root, command, remaining, ctx)`` walks the database tree, reads
the identifiers and curated params from the typed arguments, picks the most
specific URL template that can be filled and renders it.  It never raises
for user input.
"""

import logging
import re

from awscli.customizations.open_the_console_to_this import args, db, params
from awscli.customizations.open_the_console_to_this import urls as _urls

LOG = logging.getLogger(__name__)

FALLBACK_SOURCE = 'resolver:fallback'
FALLBACK_PATH = 'aws'
GO_VIEW_TEMPLATE = (
    'https://{host}/go/view?service={service:query}&region={region}'
)
# ``{ids}`` / ``{ids:enc}``: each value is encoded on its own and the
# results are comma-joined, which ``urls.render`` cannot express, so the
# placeholder is rewritten to a pre-encoded raw parameter.
_IDS_PLACEHOLDER = re.compile(r'\{ids(?::([^{}]*))?\}')
_ACCOUNT_PLACEHOLDER = re.compile(r'\{account(?::[^{}]*)?\}')
_IDS_PARAM = '_ids_{}'
# Built-in names a curated param may not replace.
_RESERVED = frozenset(['host', 'region', 'account', 'id', 'ids'])


class Context:
    """Where the console is: region, partition and a lazy account id.

    ``account_id`` is a zero-argument callable returning the account id
    or None; the resolver calls it at most once, and only when the chosen
    template contains ``{account}``.
    """

    def __init__(self, region, partition, account_id=None):
        self.region = region
        self.partition = partition
        self.account_id = account_id if account_id is not None else _none

    def __repr__(self):
        return (
            f'Context(region={self.region!r}, '
            f'partition={self.partition!r})'
        )


def _none():
    return None


class Decision:
    """The URL chosen for a command and why."""

    __slots__ = ('url', 'node_path', 'source', 'verb', 'params', 'explanation')

    def __init__(self, url, node_path, source, verb, params, explanation):
        self.url = url
        self.node_path = node_path
        self.source = source
        self.verb = verb
        self.params = params
        self.explanation = explanation

    def _fields(self):
        return tuple(getattr(self, name) for name in self.__slots__)

    def __eq__(self, other):
        if not isinstance(other, Decision):
            return NotImplemented
        return self._fields() == other._fields()

    def __repr__(self):
        inner = ', '.join(
            f'{name}={getattr(self, name)!r}' for name in self.__slots__
        )
        return f'Decision({inner})'


def resolve(root, command, remaining, ctx):
    """Return the :class:`Decision` for ``aws <command> <remaining...>``."""
    host = _urls.console_host(ctx.partition)
    base = {'host': host, 'region': ctx.region}
    node = None
    try:
        tokens = [command] + list(remaining or ())
        node, consumed, rest = db.find_node(root, tokens)
        if consumed == 0:
            return _go_view(command, base)
        return _resolve_node(node, rest, base, ctx)
    except Exception:
        LOG.debug('Unexpected error resolving %r', command, exc_info=True)
        return _last_resort(node, base)


def _go_view(command, base):
    url = _urls.render(GO_VIEW_TEMPLATE, dict(base, service=command))
    return Decision(
        url=url,
        node_path=FALLBACK_PATH,
        source=FALLBACK_SOURCE,
        verb='home',
        params={},
        explanation=(
            f'{command!r} is not a command in the database, so the '
            'console resolver go/view?service= page was used.'
        ),
    )


def _last_resort(node, base):
    """The node's best page, else the console home; never raises."""
    if isinstance(node, dict):
        try:
            url = _urls.render(node['url']['best'], base)
            return Decision(
                url=url,
                node_path=node.get('path') or FALLBACK_PATH,
                source=node['url'].get('source') or FALLBACK_SOURCE,
                verb=_verb(node),
                params={},
                explanation=(
                    'An unexpected error occurred, so the url.best '
                    f'template of {node.get("path")} was used.'
                ),
            )
        except Exception:
            LOG.debug('url.best of %r failed', node.get('path'), exc_info=True)
    return Decision(
        url=_urls.console_home(base['host'], base['region']),
        node_path=FALLBACK_PATH,
        source=FALLBACK_SOURCE,
        verb='home',
        params={},
        explanation='No template could be rendered, so the console home '
        'page was used.',
    )


def _verb(node):
    intent = node.get('intent') or {}
    return intent.get('verb') or 'home'


def _resolve_node(node, rest, base, ctx):
    path = node.get('path') or FALLBACK_PATH
    intent = node.get('intent') or {}
    url = node.get('url') or {}
    parsed = args.parse_remaining(
        rest,
        node.get('positional') or [],
        flags=node.get('flags', ()),
        scalars=node.get('scalars', ()),
    )
    resolved = _intent_params(intent, parsed)
    values = dict(resolved)
    if 'ids' in values:
        values.update(_encoded_ids(values['ids']))
    account = _LazyAccount(ctx.account_id)

    for name, template in _candidates(url, resolved):
        if not template:
            continue
        rendered = _render(template, dict(base, **values), account)
        if rendered is None:
            continue
        return Decision(
            url=rendered,
            node_path=path,
            source=url.get('source') or FALLBACK_SOURCE,
            verb=_verb(node),
            params=resolved,
            explanation=f'{path}: used the {name} template.',
        )
    decision = _last_resort(None, base)
    decision.node_path = path
    decision.explanation = (
        f'{path}: no template could be rendered (url.best failed), so the '
        'console home page was used.'
    )
    return decision


def _lookup(parsed, arg):
    values = parsed.options.get(arg.lstrip('-'))
    if values is None:
        values = parsed.positional_values.get(arg)
    return values


def _intent_params(intent, parsed):
    """Return the curated params plus ``id``/``ids`` that are present."""
    resolved = {}
    for name, spec in sorted((intent.get('params') or {}).items()):
        spec = spec or {}
        values = _lookup(parsed, spec.get('arg') or name)
        # A bare flag gives an empty list and still reaches the parse
        # function, so ``present`` works; the others return None for it.
        if values is None:
            continue
        try:
            value = params.parse_param(spec.get('parse'), values)
        except KeyError:
            LOG.debug('Unknown parse function %r', spec.get('parse'))
            continue
        if value is not None and name not in _RESERVED:
            resolved[name] = value
    for arg in intent.get('id_args') or ():
        values = _lookup(parsed, arg)
        if values:
            resolved['id'] = values[0]
            if len(values) >= 2:
                resolved['ids'] = list(values)
            break
    return resolved


def _encoded_ids(ids):
    out = {}
    for enc in ('path', 'query', 'raw'):
        template = '{v:' + enc + '}'
        encoded = [_urls.render(template, {'v': value}) for value in ids]
        out[_IDS_PARAM.format(enc)] = ','.join(encoded)
    return out


def _candidates(url, resolved):
    """Yield ``(name, template)`` in the order of the template chain."""
    present = set(resolved)
    for index, variant in enumerate(url.get('variants') or ()):
        when = variant.get('when') or ()
        if set(when) <= present:
            yield (
                f'url.variants[{index}] (when {list(when)})',
                variant.get('template'),
            )
    several = 'ids' in resolved
    if several and url.get('with_ids'):
        yield 'url.with_ids', url['with_ids']
    # Several ids: the filtered list (url.with_ids) or, when there is none
    # or it cannot be rendered, the list page (url.best); never the detail
    # page of the first id (plan decision "Several ids").
    if 'id' in resolved and url.get('with_id') and not several:
        yield 'url.with_id', url['with_id']
    yield 'url.best', url.get('best')


class _LazyAccount:
    """Call the account callable at most once."""

    def __init__(self, func):
        self._func = func
        self._called = False
        self._value = None

    def get(self):
        if not self._called:
            self._called = True
            try:
                value = self._func()
            except Exception:
                LOG.debug('Account id lookup failed', exc_info=True)
                value = None
            self._value = str(value) if value else None
        return self._value


def _render(template, values, account):
    """Render ``template``; None when a placeholder cannot be filled."""
    template = _IDS_PLACEHOLDER.sub(
        lambda m: '{' + _IDS_PARAM.format(m.group(1) or 'path') + ':raw}',
        template,
    )
    if _ACCOUNT_PLACEHOLDER.search(template):
        account_id = account.get()
        if account_id is None:
            return None
        values['account'] = account_id
    try:
        return _urls.render(template, values)
    except KeyError:
        return None
