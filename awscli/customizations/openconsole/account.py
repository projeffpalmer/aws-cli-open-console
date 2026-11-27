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
"""The identity of the credentials the console is opened with.

It comes from AWS STS ``GetCallerIdentity``, which is called only when
the identity is asked for, and at most once.
"""

import logging

from botocore.exceptions import BotoCoreError, ClientError

LOG = logging.getLogger(__name__)


class AccountResolver:
    def __init__(self, session, region):
        self._session = session
        self._region = region
        self._identity = None

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
