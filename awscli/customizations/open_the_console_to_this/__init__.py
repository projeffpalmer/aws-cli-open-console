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
"""Open the AWS console page for an AWS CLI command (``--in-console``).

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
    ``--in-console`` is given. Returns the exit code.
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

    region = session.get_config_variable('region')
    if not region:
        region = DEFAULT_REGION
        LOG.debug('Console: no region configured, using %s', region)
    partition = urls.partition_for_region(session, region)

    account_resolver = AccountResolver(session, region)
    ctx = resolver.Context(region, partition, account_id=account_resolver.get)
    decision = resolver.resolve(root, command, remaining, ctx)
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
    return browser.deliver(decision.url, open_url, session)


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
