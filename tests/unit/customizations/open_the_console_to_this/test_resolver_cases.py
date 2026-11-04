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
"""Table-driven resolver cases against the committed database.

Every ``cases/*.yaml`` file holds a list of cases (contract section 5)::

    - argv: [ec2, describe-instances, --instance-ids, i-0123456789abcdef0]
      url: "https://us-west-2.console.aws.amazon.com/ec2/home?..."
      source: resolver:list+view   # optional
      region: us-west-2            # default us-west-2
      partition: aws               # default aws
      account: "123456789012"      # default: no account available

Each case becomes one parametrized test.  ``load_cases`` and ``run_case``
are also used by ``scripts/validate-console-overrides``.
"""

import os

import pytest
from ruamel.yaml import YAML

from awscli.customizations.open_the_console_to_this import db
from awscli.customizations.open_the_console_to_this.resolver import (
    Context,
    resolve,
)

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cases')
DEFAULT_REGION = 'us-west-2'
DEFAULT_PARTITION = 'aws'
REQUIRED_KEYS = frozenset(['argv', 'url'])
CASE_KEYS = REQUIRED_KEYS | frozenset(
    ['source', 'region', 'partition', 'account']
)


class CaseFileError(ValueError):
    """A case file is malformed; the message names the file and case."""


def case_files(names=None):
    """Return the sorted case file paths, or those for ``names``.

    ``names`` are file stems (``services`` for ``cases/services.yaml``);
    a name without a file raises :class:`CaseFileError`.
    """
    if names:
        paths = []
        for name in names:
            path = os.path.join(CASES_DIR, f'{name}.yaml')
            if not os.path.isfile(path):
                raise CaseFileError(f'no case file for {name!r}: {path}')
            paths.append(path)
        return paths
    return sorted(
        os.path.join(CASES_DIR, filename)
        for filename in os.listdir(CASES_DIR)
        if filename.endswith('.yaml')
    )


def load_case_file(path):
    """Return ``[(case_id, case)]`` for one YAML file, checking its shape."""
    yaml = YAML(typ='safe', pure=True)
    with open(path, encoding='utf-8') as f:
        data = yaml.load(f)
    stem = os.path.splitext(os.path.basename(path))[0]
    if data is None:
        return []
    if not isinstance(data, list):
        raise CaseFileError(f'{path}: the top level must be a list of cases')
    cases = []
    for index, case in enumerate(data):
        where = f'{path}: case {index}'
        if not isinstance(case, dict):
            raise CaseFileError(f'{where}: expected a mapping')
        missing = sorted(REQUIRED_KEYS - set(case))
        unknown = sorted(set(case) - CASE_KEYS)
        if missing or unknown:
            raise CaseFileError(
                f'{where}: missing keys {missing}, unknown keys {unknown}'
            )
        argv = case['argv']
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(token, str) for token in argv)
        ):
            raise CaseFileError(f'{where}: argv must be a list of strings')
        if not isinstance(case['url'], str):
            raise CaseFileError(f'{where}: url must be a string')
        case_id = f'{stem}[{index}] {" ".join(argv)}'
        cases.append((case_id, dict(case)))
    return cases


def load_cases(names=None):
    """Return ``[(case_id, case)]`` from every (or the named) case file."""
    cases = []
    for path in case_files(names):
        cases.extend(load_case_file(path))
    return cases


def case_context(case):
    account = case.get('account')
    if account is not None:
        account = str(account)
    return Context(
        region=str(case.get('region', DEFAULT_REGION)),
        partition=str(case.get('partition', DEFAULT_PARTITION)),
        account_id=lambda: account,
    )


def run_case(root, case):
    """Resolve one case; return ``(decision, problems)``.

    ``problems`` is a list of strings, empty when the case passes.
    """
    argv = case['argv']
    decision = resolve(root, argv[0], argv[1:], case_context(case))
    problems = []
    if decision.url != case['url']:
        problems.append(f'url: expected {case["url"]} got {decision.url}')
    if 'source' in case and decision.source != case['source']:
        problems.append(
            f'source: expected {case["source"]} got {decision.source}'
        )
    return decision, problems


CASES = load_cases()


def test_case_files_exist():
    assert CASES, f'no cases under {CASES_DIR}'


@pytest.mark.parametrize(
    'case', [case for _, case in CASES], ids=[case_id for case_id, _ in CASES]
)
def test_resolver_case(case):
    decision, problems = run_case(db.load_db()['root'], case)
    assert not problems, f'{problems} ({decision.explanation})'
