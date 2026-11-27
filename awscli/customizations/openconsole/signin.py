# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
"""Sign the browser in to the console with the CLI's own credentials.
Credentials come from ``session.get_credentials()``, so they follow the
CLI's precedence chain.
"""

import contextlib
import hashlib
import json
import logging
from urllib.parse import quote_plus

from botocore.awsrequest import AWSRequest
from botocore.exceptions import BotoCoreError, ClientError
from botocore.history import get_global_history_recorder
from botocore.httpsession import URLLib3Session
from botocore.utils import get_environ_proxies

from awscli.customizations.openconsole import urls

LOG = logging.getLogger(__name__)

ISSUER = 'open-the-console-to-this'
FEDERATION_POLICY = (
    '{"Version":"2012-10-17","Statement":'
    '[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
)
FEDERATION_DURATION_SECONDS = 3600
# Providers whose temporary credentials are always role sessions.
ROLE_SESSION_PROVIDERS = frozenset(
    (
        'assume-role',
        'assume-role-with-web-identity',
        'container-role',
        'iam-role',
        'sso',
    )
)
_IDENTITY_KINDS = {'root': 'root user', 'user': 'IAM user'}
HASH_DIGITS = 16
HTTP_TIMEOUT_SECONDS = 25
NO_SIGNIN = 'Opening the console without signing in.'
NO_CREDENTIALS_WARNING = f'Unable to locate credentials. {NO_SIGNIN}'


class SigninError(Exception):
    """Sign-in failed; ``reason`` is short, human and free of secrets."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SigninCredentials:
    """Frozen credentials plus the name of the provider that gave them.

    ``repr`` shows only the provider name, so the object is safe to log.
    """

    __slots__ = ('access_key', 'secret_key', 'token', 'method')

    def __init__(self, access_key, secret_key, token, method=None):
        self.access_key = access_key
        self.secret_key = secret_key
        self.token = token
        self.method = method

    def __repr__(self):
        return (
            f'SigninCredentials(method={self.method!r}, '
            f'temporary={bool(self.token)})'
        )


def hashed(secret):
    """Return the stand-in that is shown instead of ``secret``."""
    digest = hashlib.sha256(secret.encode('utf-8')).hexdigest()
    return f'sha256:{digest[:HASH_DIGITS]}'


class SigninUrl:
    """The console login URL, whose sign-in token is a bearer secret."""

    __slots__ = ('_host', '_destination', '_token')

    def __init__(self, host, destination, token):
        self._host = host
        self._destination = destination
        self._token = token

    def _with_token(self, token):
        return (
            f'https://{self._host}/federation?Action=login'
            f'&Issuer={quote_plus(ISSUER)}'
            f'&Destination={quote_plus(self._destination)}'
            f'&SigninToken={token}'
        )

    def unhashed(self):
        """Return the URL that signs in.  For launching the browser only."""
        return self._with_token(quote_plus(self._token))

    def __str__(self):
        return self._with_token(hashed(self._token))

    def __repr__(self):
        return f'SigninUrl({str(self)!r})'

    def hashed_in(self, text):
        """Return ``text`` with the token hashed wherever it is quoted."""
        stand_in = hashed(self._token)
        forms = {self._token, quote_plus(self._token)}
        for form in sorted(forms, key=len, reverse=True):
            text = text.replace(form, stand_in)
        return text


def _warning(message):
    # The warning is one line; provider messages can span several.
    message = ' '.join((message or '').split()).rstrip('.')
    return f'{message}. {NO_SIGNIN}'


def resolve_credentials(session):
    """Return ``(SigninCredentials or None, warning or None)``."""
    try:
        creds = session.get_credentials()
        if creds is None:
            return None, NO_CREDENTIALS_WARNING
        frozen = creds.get_frozen_credentials()
    except (BotoCoreError, ClientError) as exc:
        LOG.debug('Credential resolution failed', exc_info=True)
        return None, _warning(str(exc) or type(exc).__name__)
    if not frozen.access_key or not frozen.secret_key:
        return None, NO_CREDENTIALS_WARNING
    method = getattr(creds, 'method', None)
    LOG.debug('Console sign-in credentials from provider: %s', method)
    return (
        SigninCredentials(
            frozen.access_key, frozen.secret_key, frozen.token, method
        ),
        None,
    )


class _DropSecretsFilter(logging.Filter):
    def __init__(self, needles):
        super().__init__()
        self._needles = [needle for needle in needles if needle]

    def filter(self, record):
        try:
            parts = [record.getMessage()]
        except Exception:
            parts = [str(record.msg)]
        exc = record.exc_info[1] if record.exc_info else None
        while exc is not None and len(parts) < 10:
            parts.append(str(exc))
            exc = exc.__cause__ or exc.__context__
        text = '\n'.join(parts)
        return not any(needle in text for needle in self._needles)


@contextlib.contextmanager
def _secrets_kept_out_of_logs(*needles):
    """Drop log records mentioning ``needles`` while the block runs."""
    drop = _DropSecretsFilter(needles)
    handlers = set(logging.getLogger().handlers)
    for logger in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    for handler in handlers:
        handler.addFilter(drop)
    try:
        yield
    finally:
        for handler in handlers:
            handler.removeFilter(drop)


def _verify(session):
    """Return the TLS ``verify`` value for the sign-in request."""
    verify = session.get_config_variable('ca_bundle')
    if verify is None or verify is True:
        return True
    if isinstance(verify, str) and verify.strip():
        return verify
    raise SigninError('invalid ca_bundle configuration')


def _http_get(session, url):
    """GET ``url`` and return ``(status_code, text)``."""
    verify = _verify(session)
    http = URLLib3Session(
        verify=verify,
        proxies=get_environ_proxies(url),
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    try:
        response = http.send(AWSRequest(method='GET', url=url).prepare())
        return response.status_code, response.text
    finally:
        http.close()


@contextlib.contextmanager
def _history_paused():
    """Keep the block's API calls out of ``cli_history``."""
    recorder = get_global_history_recorder()
    was_enabled = bool(getattr(recorder, '_enabled', False))
    if was_enabled:
        recorder.disable()
    try:
        yield
    finally:
        if was_enabled:
            recorder.enable()


def _federation_token(session, creds, region):
    try:
        client = session.create_client('sts', region_name=region)
        with _history_paused():
            with _secrets_kept_out_of_logs(
                creds.secret_key, 'SecretAccessKey', 'SessionToken'
            ):
                response = client.get_federation_token(
                    Name=ISSUER,
                    Policy=FEDERATION_POLICY,
                    DurationSeconds=FEDERATION_DURATION_SECONDS,
                )
    except ClientError as exc:
        error = exc.response.get('Error', {})
        code = error.get('Code') or 'error'
        message = error.get('Message')
        reason = f'GetFederationToken failed: {code}'
        if message:
            reason = f'{reason}: {message}'
        raise SigninError(reason)
    except BotoCoreError as exc:
        raise SigninError(f'GetFederationToken failed: {exc}')
    try:
        issued = response['Credentials']
        federated = SigninCredentials(
            issued['AccessKeyId'],
            issued['SecretAccessKey'],
            issued['SessionToken'],
            creds.method,
        )
    except (KeyError, TypeError):
        raise SigninError('unexpected GetFederationToken response')
    return federated


def _check_role_session(creds, account_resolver):
    """Refuse temporary credentials the console will not federate."""
    if creds.method in ROLE_SESSION_PROVIDERS or account_resolver is None:
        return
    arn = account_resolver.caller_arn()
    if arn is None:
        return
    fields = arn.split(':', 5)
    resource = fields[5] if len(fields) == 6 else ''
    kind = resource.split('/', 1)[0]
    if fields[2:3] == ['sts'] and kind in ('assumed-role', 'federated-user'):
        return
    raise SigninError(
        f'{_IDENTITY_KINDS.get(kind, kind or "unknown")} session credentials '
        'cannot sign in to the console through federation; only role and '
        'federated user sessions can'
    )


def _signin_token(session, creds, host):
    session_json = json.dumps(
        {
            'sessionId': creds.access_key,
            'sessionKey': creds.secret_key,
            'sessionToken': creds.token,
        }
    )
    encoded = quote_plus(session_json)
    url = f'https://{host}/federation?Action=getSigninToken&Session={encoded}'
    try:
        with _secrets_kept_out_of_logs(
            creds.secret_key, creds.token, encoded, 'getSigninToken'
        ):
            status, text = _http_get(session, url)
    except Exception as exc:
        # The exception text can contain the URL, so only its type is used.
        raise SigninError(f'could not reach {host}: {type(exc).__name__}')
    if status != 200:
        raise SigninError(f'{host} returned HTTP {status}')
    try:
        token = json.loads(text).get('SigninToken')
    except (ValueError, TypeError, AttributeError):
        raise SigninError(f'unexpected response from {host}')
    if not token or not isinstance(token, str):
        raise SigninError(f'no sign-in token in the response from {host}')
    return token


def federation_login_url(
    session, creds, destination, partition, region, account_resolver
):
    """Return the console login URL for ``destination`` as a ``SigninUrl``."""
    host = urls.signin_host(partition)
    # Checked before any request, so a blank ca_bundle never sends the
    # credentials without certificate verification.
    _verify(session)
    if creds.token:
        _check_role_session(creds, account_resolver)
    else:
        LOG.debug('Long-term keys: calling STS GetFederationToken first')
        creds = _federation_token(session, creds, region)
    token = _signin_token(session, creds, host)
    return SigninUrl(host, destination, token)


def wrap(session, destination, partition, region, account_resolver):
    """Return ``(url_to_open, warning or None)``."""
    creds, warning = resolve_credentials(session)
    if creds is None:
        LOG.debug('Console sign-in not applied: no credentials')
        return destination, warning
    try:
        login_url = federation_login_url(
            session, creds, destination, partition, region, account_resolver
        )
    except SigninError as exc:
        LOG.debug('Console sign-in not applied: %s', exc.reason)
        return destination, (
            f'Console sign-in failed ({exc.reason}). {NO_SIGNIN}'
        )
    LOG.debug('Console sign-in applied')
    return login_url, None
