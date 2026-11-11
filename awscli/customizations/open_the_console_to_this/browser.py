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
"""Print the console URL and open the browser (contract section 4).

stdout gets exactly one line: the console destination URL, while the
browser gets the URL to open (the sign-in URL when sign-in was applied).
In print-only mode the browser is not opened and the URL to open is the
printed line, so it can be pasted somewhere else.
"""

import logging
import os
import sys
import webbrowser

from awscli.customizations.sso.utils import original_ld_library_path
from awscli.customizations.utils import uni_print

LOG = logging.getLogger(__name__)

CONFIG_KEY = 'in_console_open'
ENV_VAR = 'AWS_IN_CONSOLE_OPEN'
FALSE_VALUES = frozenset(['false', '0', 'no', 'off'])
DISPLAY_VARS = ('DISPLAY', 'WAYLAND_DISPLAY')
NEEDS_DISPLAY_PLATFORMS = ('linux', 'freebsd', 'openbsd', 'netbsd')
NO_BROWSER_REASON = 'no runnable browser found'


def _is_false(value):
    if value is False:
        return True
    return isinstance(value, str) and value.strip().lower() in FALSE_VALUES


def _config_value(session):
    try:
        return (session.get_scoped_config() or {}).get(CONFIG_KEY)
    except Exception:
        LOG.debug('Could not read %s from the config', CONFIG_KEY)
        return None


def _no_display():
    if not sys.platform.startswith(NEEDS_DISPLAY_PLATFORMS):
        return False
    return not any(os.environ.get(name) for name in DISPLAY_VARS)


def print_only(session):
    """Return True when the URL is printed and no browser is opened."""
    if _is_false(os.environ.get(ENV_VAR)):
        LOG.debug('Print-only: %s is false', ENV_VAR)
        return True
    if _is_false(_config_value(session)):
        LOG.debug('Print-only: %s is false in the config', CONFIG_KEY)
        return True
    if _no_display():
        LOG.debug('Print-only: no DISPLAY or WAYLAND_DISPLAY')
        return True
    return False


def deliver(console_url, open_url, session):
    """Print one line and open ``open_url`` unless print-only; return 0."""
    if print_only(session):
        uni_print(open_url + '\n')
        return 0
    uni_print(console_url + '\n')
    sys.stdout.flush()
    reason = _open_browser(open_url)
    if reason is not None:
        uni_print(
            f'Could not open a browser ({reason}); the URL is printed '
            'above.\n',
            sys.stderr,
        )
    return 0


def open_beside_output(console_url, open_url, session):
    """Open ``open_url`` for ``--open-console``; stdout stays the command's.

    In print-only mode the URL to open goes to stderr instead. A browser
    that cannot be opened gives a warning naming ``console_url`` (never the
    sign-in URL, a bearer secret).
    """
    if print_only(session):
        uni_print(open_url + '\n', sys.stderr)
        return
    reason = _open_browser(open_url)
    if reason is not None:
        uni_print(
            f'Could not open a browser ({reason}); the console page is '
            f'{console_url}\n',
            sys.stderr,
        )


def _open_browser(open_url):
    """Open ``open_url`` in a new tab; return None or the failure reason."""
    try:
        # ``webbrowser`` returns False (it does not raise) when it finds no
        # runnable browser, so the result is checked here.
        with original_ld_library_path():
            opened = webbrowser.open_new_tab(open_url)
    except (webbrowser.Error, OSError) as exc:
        # The URL can be a sign-in bearer secret: keep it out of the text.
        LOG.debug('Opening the browser failed: %s', type(exc).__name__)
        return (str(exc) or type(exc).__name__).replace(open_url, '<url>')
    if opened is False:
        LOG.debug('Opening the browser failed: no runnable browser')
        return NO_BROWSER_REASON
    return None
