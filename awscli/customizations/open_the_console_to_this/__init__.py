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
"""Open the AWS console page for an AWS CLI command (``--console-link``).

The modules of this package resolve a typed CLI command to a console or
documentation URL using the database in
``awscli/data/open_the_console_to_this/commands.json``.
"""

import logging
import sys

LOG = logging.getLogger(__name__)

DEFAULT_REGION = 'us-east-1'
HELP_TOKEN = 'help'


def open_console(session, parsed_args, remaining):
    """Open the console (or docs) page for the typed command.

    Called from ``CLIDriver.main()`` instead of running the command when
    ``--console-link`` is given. Returns the exit code.
    """
    # Imported here so that importing this package stays cheap and safe.
    from awscli.customizations.open_the_console_to_this import (
        args,
        browser,
        db,
        docs,
        resolver,
        signin,
        urls,
    )
    from awscli.customizations.open_the_console_to_this.account import (
        AccountResolver,
    )
    from awscli.customizations.utils import uni_print

    command = parsed_args.command
    remaining = list(remaining or ())
    try:
        root = db.load_db()['root']
    except (OSError, ValueError) as exc:
        uni_print(
            'Unable to load the console URL database: '
            f'{db.DB_PATH}: {exc}\n',
            sys.stderr,
        )
        return 255

    node, _, rest = db.find_node(root, [command] + remaining)
    if command == HELP_TOKEN or _help_positional(args, node, rest):
        url = docs.docs_url(root, node, rest)
        LOG.debug(
            'Console: documentation for %s: %s',
            node.get('path') or 'aws',
            url,
        )
        return browser.deliver(url, url, session)

    region, partition = _location(session, urls)
    account_resolver = AccountResolver(session, region)
    ctx = resolver.Context(region, partition, account_id=account_resolver.get)
    decision = resolver.resolve(root, command, remaining, ctx)
    open_url = _sign_in(
        session, decision, partition, region, account_resolver, signin
    )
    return browser.deliver(decision.url, open_url, session)


def run_and_open(session, parsed_args, remaining, command_callable):
    """Run the command, then open the page of the resource it acted on.

    Called from ``CLIDriver.main()`` when ``--open-console`` is given. The
    command runs exactly as without the flag and its return code is
    returned. For an API operation ``CLIOperationCaller.invoke`` hands the
    response to the :class:`ConsoleOpener` set on ``parsed_args`` before
    the response is displayed; any other command that succeeds opens the
    page its typed arguments resolve to once it has finished. ``help``
    only shows help.
    """
    from awscli.customizations.open_the_console_to_this import args, db

    remaining = list(remaining or ())
    command = parsed_args.command
    try:
        node, _, rest = db.find_node(
            db.load_db()['root'], [command] + remaining
        )
        wants_help = command == HELP_TOKEN or _help_positional(
            args, node, rest
        )
    except Exception:
        LOG.debug('Console: database not usable', exc_info=True)
        wants_help = False
    if wants_help:
        return command_callable(remaining, parsed_args)
    opener = ConsoleOpener(session, command, remaining)
    parsed_args.console_opener = opener
    rc = command_callable(remaining, parsed_args)
    if rc in (0, None) and not opener.done:
        opener.open(None)
    return rc


class ConsoleOpener:
    """Opens the console page once for an ``--open-console`` command."""

    def __init__(self, session, command, remaining):
        self._session = session
        self._command = command
        self._remaining = list(remaining)
        self.done = False

    def before_display(self, response):
        """Open the page for ``response``; return what to display.

        A paginated response is fetched once here and replayed to the
        formatter, so no page is requested twice. Errors fetching pages
        are the command's own and propagate; console errors only warn.
        """
        if self.done:
            return response
        from awscli.formatter import is_response_paginated

        if is_response_paginated(response):
            pages = [_page(page) for page in response]
            replayed = _replay(response, pages)
            self.open(pages)
            return replayed
        self.open(response)
        return response

    def open(self, response):
        """Resolve, sign in and open; never raises."""
        self.done = True
        from awscli.customizations.utils import uni_print

        try:
            self._open(response)
        except Exception as exc:
            LOG.debug('Console: opening failed', exc_info=True)
            uni_print(
                f'Could not open the console ({exc or type(exc).__name__}).'
                '\n',
                sys.stderr,
            )

    def _open(self, response):
        from awscli.customizations.open_the_console_to_this import (
            browser,
            db,
            follow,
            resolver,
            signin,
            urls,
        )
        from awscli.customizations.open_the_console_to_this.account import (
            AccountResolver,
        )

        session = self._session
        root = db.load_db()['root']
        region, partition = _location(session, urls)
        account_resolver = AccountResolver(session, region)
        ctx = resolver.Context(
            region, partition, account_id=account_resolver.get
        )
        decision = follow.resolve_after_run(
            root, self._command, self._remaining, response, ctx
        )
        open_url = _sign_in(
            session, decision, partition, region, account_resolver, signin
        )
        browser.open_beside_output(decision.url, open_url, session)


def _page(page):
    # Operation-object pagination yields (http_response, parsed) pairs.
    if isinstance(page, tuple) and len(page) == 2:
        return page[1]
    return page


def _replay(page_iterator, pages):
    """A page iterator that yields the pages already fetched."""
    replayed = object.__new__(_replay_class(type(page_iterator)))
    replayed.__dict__.update(page_iterator.__dict__)
    replayed._replay_pages = list(pages)
    return replayed


_REPLAY_CLASSES = {}


def _replay_class(base):
    if base not in _REPLAY_CLASSES:

        def __iter__(self):
            return iter(self._replay_pages)

        _REPLAY_CLASSES[base] = type(
            'Replayed' + base.__name__, (base,), {'__iter__': __iter__}
        )
    return _REPLAY_CLASSES[base]


def _location(session, urls):
    region = session.get_config_variable('region')
    if not region:
        region = DEFAULT_REGION
        LOG.debug('Console: no region configured, using %s', region)
    return region, urls.partition_for_region(session, region)


def _sign_in(session, decision, partition, region, account_resolver, signin):
    """Return the URL to open; a sign-in warning goes to stderr."""
    from awscli.customizations.utils import uni_print

    LOG.debug(
        'Console: node=%s source=%s verb=%s params=%r',
        decision.node_path,
        decision.source,
        decision.verb,
        decision.params,
    )
    open_url, warning = signin.wrap(
        session, decision.url, partition, region, account_resolver
    )
    if warning:
        uni_print(warning + '\n', sys.stderr)
    signed_in = warning is None and open_url != decision.url
    LOG.debug(
        'Console: sign-in applied=%s, credential method=%s',
        signed_in,
        _credential_method(session, warning, signin),
    )
    return open_url


def _help_positional(args, node, rest):
    """True when ``help`` is a positional, not an option value.

    ``rest`` is parsed with the node's positional names, flags and
    scalars exactly as ``resolver.resolve`` does, so ``--function-name
    help`` is a value while ``s3 ls s3://bucket help`` asks for help.
    """
    parsed = args.parse_remaining(
        rest,
        node.get('positional') or [],
        flags=node.get('flags', ()),
        scalars=node.get('scalars', ()),
    )
    return parsed.help


def _credential_method(session, warning, signin):
    """The provider name of the already resolved credentials, if any.

    Only asked when ``signin.wrap`` resolved credentials (the session
    caches them), so this never runs the provider chain a second time.
    """
    if warning is not None and not warning.startswith(
        'Console sign-in failed'
    ):
        return None
    try:
        return getattr(session.get_credentials(), 'method', None)
    except Exception:
        return None
