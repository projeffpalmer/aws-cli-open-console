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
"""Open the AWS console page for an AWS CLI command.

``--console-link`` opens the page instead of running the command.
``--open-console`` opens it after the command runs. The page is chosen
at runtime.
"""

import logging
import sys
import traceback

LOG = logging.getLogger(__name__)

DEFAULT_REGION = 'us-east-1'


def open_console(session, parsed_args, remaining):
    """Open the console (or docs) page for the typed command.

    Called from ``CLIDriver.main()`` instead of running the command when
    ``--console-link`` is given. Returns the exit code.
    """
    # Imported here so that importing this package stays cheap and safe.
    from awscli.customizations.open_the_console_to_this import (
        browser,
        docs,
        resolver,
        signin,
        urls,
    )
    from awscli.customizations.open_the_console_to_this.account import (
        AccountResolver,
    )

    command = parsed_args.command
    remaining = list(remaining or ())
    if resolver.is_help(command, remaining, session):
        url = docs.docs_url(command, remaining, session)
        LOG.debug('Console: documentation for %s: %s', command, url)
        return browser.deliver(url, url, session)

    region, partition, account_resolver, ctx = _console_context(
        session, urls, resolver, AccountResolver
    )
    decision = resolver.resolve(command, remaining, ctx)
    open_url = _sign_in(
        session, decision, partition, region, account_resolver, signin, browser
    )
    return browser.deliver(decision.url, open_url, session)


def run_and_open(session, parsed_args, remaining, command_callable):
    """Run the command, then open the page of the resource it acted on.

    Called from ``CLIDriver.main()`` when ``--open-console`` is given. The
    command runs exactly as without the flag, including displaying its
    output, and its return code is returned. The console opens only after
    that command has completed successfully. 
    """
    from awscli.customizations.open_the_console_to_this import resolver

    remaining = list(remaining or ())
    command = parsed_args.command
    wants_help = resolver.is_help(command, remaining, session)
    if wants_help:
        return command_callable(remaining, parsed_args)
    opener = ConsoleOpener(session, command, remaining)
    parsed_args.console_opener = opener
    rc = command_callable(remaining, parsed_args)
    if rc in (0, None):
        opener.open(opener.response_to_open())
    return rc


class ConsoleOpener:
    """Opens the console page once for an ``--open-console`` command."""

    def __init__(self, session, command, remaining):
        self._session = session
        self._command = command
        self._remaining = list(remaining)
        self._open_url = None
        self._response = None
        self._has_response = False
        self.done = False

    def before_display(self, response):
        """Remember ``response`` and return what to display.

        A paginated response is fetched once here and replayed to the
        formatter, so no page is requested twice.
        """
        if self._has_response:
            return response
        from awscli.formatter import is_response_paginated

        if is_response_paginated(response):
            pages = [_page(page) for page in response]
            self._response = pages
            self._has_response = True
            return _replay(response, pages)
        self._response = response
        self._has_response = True
        return response

    def response_to_open(self):
        """The captured API response, or None when there was none."""
        return self._response

    def open(self, response):
        """Resolve, sign in and open; never raises."""
        if self.done:
            return
        self.done = True
        from awscli.customizations.utils import uni_print

        try:
            self._open(response)
        except Exception as exc:
            LOG.debug(
                'Console: opening failed\n%s',
                self._token_hashed(traceback.format_exc()),
            )
            reason = self._token_hashed(str(exc) or type(exc).__name__)
            uni_print(f'Could not open the console ({reason}).\n', sys.stderr)

    def _token_hashed(self, text):
        """Return ``text`` hashed.
        """
        if self._open_url is None or isinstance(self._open_url, str):
            return text
        return self._open_url.hashed_in(text)

    def _open(self, response):
        from awscli.customizations.open_the_console_to_this import (
            browser,
            follow,
            resolver,
            signin,
            urls,
        )
        from awscli.customizations.open_the_console_to_this.account import (
            AccountResolver,
        )

        session = self._session
        region, partition, account_resolver, ctx = _console_context(
            session, urls, resolver, AccountResolver
        )
        decision = follow.resolve_after_run(
            self._command, self._remaining, response, ctx
        )
        self._open_url = _sign_in(
            session,
            decision,
            partition,
            region,
            account_resolver,
            signin,
            browser,
        )
        browser.open_beside_output(decision.url, self._open_url, session)


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


def _console_context(session, urls, resolver, account_resolver_cls):
    region, partition = _location(session, urls)
    account_resolver = account_resolver_cls(session, region)
    ctx = resolver.Context(
        region,
        partition,
        account_id=account_resolver.get,
        session=session,
    )
    return region, partition, account_resolver, ctx


def _location(session, urls):
    region = session.get_config_variable('region')
    if not region:
        region = DEFAULT_REGION
        LOG.debug('Console: no region configured, using %s', region)
    return region, urls.partition_for_region(session, region)


def _sign_in(
    session, decision, partition, region, account_resolver, signin, browser
):
    """Return the URL to open.
    """
    from awscli.customizations.utils import uni_print

    LOG.debug(
        'Console: node=%s source=%s verb=%s params=%r',
        decision.node_path,
        decision.source,
        decision.verb,
        decision.params,
    )
    if browser.print_only(session):
        LOG.debug('Console: sign-in not attempted in print-only mode')
        return decision.url
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


def _credential_method(session, warning, signin):
    """The provider name of the already resolved credentials, if any.
    """
    if warning is not None and not warning.startswith(
        'Console sign-in failed'
    ):
        return None
    try:
        return getattr(session.get_credentials(), 'method', None)
    except Exception:
        return None
