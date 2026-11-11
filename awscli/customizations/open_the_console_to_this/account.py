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
"""The account id of the credentials the console is opened with.

The id comes from the identity of the resolved credentials, never from
profile keys such as ``sso_account_id`` (they can disagree with
higher-precedence credentials): the ``GetFederationToken`` response ARN
when sign-in makes that call anyway, else one STS ``GetCallerIdentity``
call, cached for the life of the process (a failure is cached as None).
"""

import logging
import re

from botocore.exceptions import BotoCoreError, ClientError

LOG = logging.getLogger(__name__)

_ACCOUNT_ID = re.compile(r'\d{12}')


def _account_from_arn(arn):
    if not isinstance(arn, str):
        return None
    fields = arn.split(':')
    if len(fields) < 6 or not _ACCOUNT_ID.fullmatch(fields[4]):
        return None
    return fields[4]


class AccountResolver:
    def __init__(self, session, region):
        self._session = session
        self._region = region
        self._account_id = None
        self._resolved = False
        self._identity = None

    def set_from_arn(self, arn):
        """Remember the account id in ``arn`` when it has a valid one."""
        account_id = _account_from_arn(arn)
        if account_id is not None:
            self._account_id = account_id
            self._resolved = True

    def _caller_identity(self):
        """The GetCallerIdentity response, ``{}`` on failure; cached."""
        if self._identity is None:
            self._identity = {}
            try:
                client = self._session.create_client(
                    'sts', region_name=self._region
                )
                identity = client.get_caller_identity()
            except (BotoCoreError, ClientError):
                LOG.debug('GetCallerIdentity failed', exc_info=True)
            else:
                if isinstance(identity, dict):
                    self._identity = identity
        return self._identity

    def caller_arn(self):
        """Return the ARN of the credentials' identity or None."""
        arn = self._caller_identity().get('Arn')
        return arn if isinstance(arn, str) else None

    def get(self):
        """Return the account id or None; STS is called at most once."""
        if self._resolved:
            return self._account_id
        self._resolved = True
        account_id = self._caller_identity().get('Account')
        if isinstance(account_id, str) and _ACCOUNT_ID.fullmatch(account_id):
            self._account_id = account_id
        else:
            LOG.debug('GetCallerIdentity returned no usable account id')
        return self._account_id
