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
"""Resolve a command that ran to the page of the resource it acted on.

Used by ``--open-console``. Identifiers come from the API response when
it names the resource, and from the typed arguments otherwise.
"""

from awscli.customizations.openconsole import resolver


def resolve_after_run(command, remaining, response, ctx):
    """Return the :class:`~resolver.Decision` for a command that ran."""
    return resolver.resolve(
        command, remaining, ctx, response=response, after_run=True
    )
