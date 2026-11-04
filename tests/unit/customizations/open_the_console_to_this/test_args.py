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
from awscli.customizations.open_the_console_to_this.args import (
    ParsedArgs,
    parse_remaining,
)
from awscli.testutils import unittest


class TestParseRemaining(unittest.TestCase):
    def parse(self, tokens, positional_names=()):
        return parse_remaining(tokens, list(positional_names))

    def test_empty(self):
        parsed = self.parse([])
        self.assertIsInstance(parsed, ParsedArgs)
        self.assertEqual(parsed.options, {})
        self.assertEqual(parsed.positionals, [])
        self.assertEqual(parsed.positional_values, {})
        self.assertFalse(parsed.help)

    def test_option_with_one_value_keeps_inner_dashes(self):
        parsed = self.parse(['--instance-ids', 'i-1'])
        self.assertEqual(parsed.options, {'instance-ids': ['i-1']})

    def test_option_collects_values_until_next_double_dash(self):
        parsed = self.parse(['--instance-ids', 'i-1', 'i-2', '--dry-run'])
        self.assertEqual(
            parsed.options, {'instance-ids': ['i-1', 'i-2'], 'dry-run': []}
        )
        self.assertEqual(parsed.positionals, [])

    def test_single_dash_tokens_are_values(self):
        parsed = self.parse(['--start', '-1', '-h'])
        self.assertEqual(parsed.options, {'start': ['-1', '-h']})

    def test_equals_form_gives_one_value(self):
        parsed = self.parse(['--queue-url=https://x/1/q', 'pos'], ['path'])
        self.assertEqual(parsed.options, {'queue-url': ['https://x/1/q']})
        self.assertEqual(parsed.positionals, ['pos'])
        self.assertEqual(parsed.positional_values, {'path': ['pos']})

    def test_equals_form_keeps_later_equals_signs(self):
        parsed = self.parse(['--filters=Name=tag,Values=a=b'])
        self.assertEqual(parsed.options, {'filters': ['Name=tag,Values=a=b']})

    def test_equals_form_with_empty_value(self):
        parsed = self.parse(['--name='])
        self.assertEqual(parsed.options, {'name': ['']})

    def test_bare_option_at_end_is_flag(self):
        parsed = self.parse(['--recursive'])
        self.assertEqual(parsed.options, {'recursive': []})

    def test_bare_option_before_option_is_flag(self):
        parsed = self.parse(['--recursive', '--page-size', '5'])
        self.assertEqual(parsed.options, {'recursive': [], 'page-size': ['5']})

    def test_repeated_options_append(self):
        parsed = self.parse(
            ['--instance-ids', 'i-1', '--instance-ids=i-2', '--instance-ids']
        )
        self.assertEqual(parsed.options, {'instance-ids': ['i-1', 'i-2']})

    def test_positionals_before_options(self):
        parsed = self.parse(['s3://b/k', '--recursive'], ['paths'])
        self.assertEqual(parsed.positionals, ['s3://b/k'])
        self.assertEqual(parsed.positional_values, {'paths': ['s3://b/k']})
        self.assertEqual(parsed.options, {'recursive': []})

    def test_tokens_after_option_values_are_values_not_positionals(self):
        parsed = self.parse(['--exclude', '*.tmp', 's3://b/'], ['paths'])
        self.assertEqual(parsed.options, {'exclude': ['*.tmp', 's3://b/']})
        self.assertEqual(parsed.positionals, [])

    def test_double_dash_makes_later_tokens_positional(self):
        parsed = self.parse(
            ['--name', 'a', '--', '--not-an-option', 'b'], ['paths']
        )
        self.assertEqual(parsed.options, {'name': ['a']})
        self.assertEqual(parsed.positionals, ['--not-an-option', 'b'])
        self.assertEqual(
            parsed.positional_values, {'paths': ['--not-an-option', 'b']}
        )

    def test_second_double_dash_is_positional(self):
        parsed = self.parse(['--', '--'])
        self.assertEqual(parsed.positionals, ['--'])

    def test_nargs_two_positional_gets_every_token(self):
        parsed = self.parse(['./local', 's3://b/k', '--dryrun'], ['paths'])
        self.assertEqual(parsed.positionals, ['./local', 's3://b/k'])
        self.assertEqual(
            parsed.positional_values, {'paths': ['./local', 's3://b/k']}
        )

    def test_positionals_assigned_to_names_in_order(self):
        parsed = self.parse(['region', 'us-west-2'], ['varname', 'value'])
        self.assertEqual(
            parsed.positional_values,
            {'varname': ['region'], 'value': ['us-west-2']},
        )
        self.assertEqual(parsed.positionals, ['region', 'us-west-2'])

    def test_last_name_takes_the_remainder(self):
        parsed = self.parse(['a', 'b', 'c'], ['first', 'rest'])
        self.assertEqual(
            parsed.positional_values, {'first': ['a'], 'rest': ['b', 'c']}
        )

    def test_names_without_tokens_are_absent(self):
        parsed = self.parse(['a'], ['first', 'second'])
        self.assertEqual(parsed.positional_values, {'first': ['a']})

    def test_positionals_without_names(self):
        parsed = self.parse(['a', 'b'])
        self.assertEqual(parsed.positionals, ['a', 'b'])
        self.assertEqual(parsed.positional_values, {})

    def test_none_positional_names(self):
        parsed = parse_remaining(['a'], None)
        self.assertEqual(parsed.positionals, ['a'])
        self.assertEqual(parsed.positional_values, {})

    def test_help_sets_flag_and_is_excluded(self):
        parsed = self.parse(['s3://b/', 'help'], ['paths'])
        self.assertTrue(parsed.help)
        self.assertEqual(parsed.positionals, ['s3://b/'])
        self.assertEqual(parsed.positional_values, {'paths': ['s3://b/']})

    def test_help_alone(self):
        parsed = self.parse(['help'], ['paths'])
        self.assertTrue(parsed.help)
        self.assertEqual(parsed.positionals, [])
        self.assertEqual(parsed.positional_values, {})

    def test_help_after_double_dash_is_a_positional_help(self):
        parsed = self.parse(['--', 'help'])
        self.assertTrue(parsed.help)
        self.assertEqual(parsed.positionals, [])

    def test_help_as_option_value_is_a_value(self):
        parsed = self.parse(['--name', 'help'])
        self.assertFalse(parsed.help)
        self.assertEqual(parsed.options, {'name': ['help']})

    def test_does_not_modify_inputs(self):
        tokens = ['a', '--k', 'v']
        names = ['paths']
        parse_remaining(tokens, names)
        self.assertEqual(tokens, ['a', '--k', 'v'])
        self.assertEqual(names, ['paths'])

    def test_repr_mentions_fields(self):
        text = repr(self.parse(['a', '--k', 'v']))
        self.assertIn("'k': ['v']", text)
        self.assertIn("positionals=['a']", text)


class TestFlagsAndScalars(unittest.TestCase):
    def test_flag_before_positional_does_not_take_it(self):
        parsed = parse_remaining(
            ['--recursive', 's3://b/p/'], ['paths'], flags=['recursive']
        )
        self.assertEqual(parsed.positionals, ['s3://b/p/'])
        self.assertEqual(parsed.positional_values, {'paths': ['s3://b/p/']})
        self.assertEqual(parsed.options, {'recursive': []})

    def test_flag_before_option(self):
        parsed = parse_remaining(
            ['--recursive', '--page-size', '5', 's3://b/'],
            ['paths'],
            flags=['recursive'],
        )
        self.assertEqual(
            parsed.options, {'recursive': [], 'page-size': ['5', 's3://b/']}
        )
        self.assertEqual(parsed.positionals, [])

    def test_flag_with_equals_keeps_its_value(self):
        parsed = parse_remaining(
            ['--recursive=true', 'x'], ['paths'], flags=['recursive']
        )
        self.assertEqual(parsed.options, {'recursive': ['true']})
        self.assertEqual(parsed.positionals, ['x'])

    def test_scalar_takes_exactly_one_value(self):
        parsed = parse_remaining(
            ['--function-name', 'f', 'out.json'],
            ['outfile'],
            scalars=['function-name'],
        )
        self.assertEqual(parsed.options, {'function-name': ['f']})
        self.assertEqual(parsed.positionals, ['out.json'])
        self.assertEqual(parsed.positional_values, {'outfile': ['out.json']})

    def test_repeated_scalar_appends(self):
        parsed = parse_remaining(
            ['--name', 'a', 'p1', '--name', 'b', 'p2'],
            ['paths'],
            scalars=['name'],
        )
        self.assertEqual(parsed.options, {'name': ['a', 'b']})
        self.assertEqual(parsed.positionals, ['p1', 'p2'])

    def test_scalar_followed_by_option_is_empty(self):
        parsed = parse_remaining(
            ['--name', '--other', 'v'], [], scalars=['name']
        )
        self.assertEqual(parsed.options, {'name': [], 'other': ['v']})

    def test_scalar_equals_form(self):
        parsed = parse_remaining(
            ['--name=a', 'p'], ['paths'], scalars=['name']
        )
        self.assertEqual(parsed.options, {'name': ['a']})
        self.assertEqual(parsed.positionals, ['p'])

    def test_other_options_stay_greedy(self):
        parsed = parse_remaining(
            ['--recursive', '--exclude', '*.tmp', 's3://b/'],
            ['paths'],
            flags=['recursive'],
            scalars=['name'],
        )
        self.assertEqual(
            parsed.options, {'recursive': [], 'exclude': ['*.tmp', 's3://b/']}
        )
        self.assertEqual(parsed.positionals, [])

    def test_without_hints_the_old_rule_holds(self):
        parsed = parse_remaining(['--recursive', 's3://b/p/'], ['paths'])
        self.assertEqual(parsed.options, {'recursive': ['s3://b/p/']})
        self.assertEqual(parsed.positionals, [])
        parsed = parse_remaining(
            ['--function-name', 'f', 'out.json'], ['outfile']
        )
        self.assertEqual(parsed.options, {'function-name': ['f', 'out.json']})
        self.assertEqual(parsed.positionals, [])

    def test_none_hints_are_empty(self):
        parsed = parse_remaining(
            ['--recursive', 'x'], ['paths'], flags=None, scalars=None
        )
        self.assertEqual(parsed.options, {'recursive': ['x']})
