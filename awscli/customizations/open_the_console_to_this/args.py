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
"""Tokenize the arguments that follow the command path."""


class ParsedArgs:
    """The result of :func:`parse_remaining`.
    ``options`` maps an option name without its leading dashes
    """

    def __init__(self):
        self.options = {}
        self.positionals = []
        self.positional_values = {}
        self.help = False

    def __repr__(self):
        return (
            f'ParsedArgs(options={self.options!r}, '
            f'positionals={self.positionals!r}, '
            f'positional_values={self.positional_values!r}, '
            f'help={self.help!r})'
        )


def parse_remaining(tokens, positional_names, flags=(), scalars=()):
    """Parse ``tokens`` into options and positionals.
    """
    flags = frozenset(flags or ())
    scalars = frozenset(scalars or ())
    result = ParsedArgs()
    current = None
    room = None
    only_positionals = False
    for token in tokens:
        if only_positionals:
            _add_positional(result, token)
        elif token == '--':
            only_positionals = True
            current = None
        elif token.startswith('--'):
            name, sep, value = token[2:].partition('=')
            values = result.options.setdefault(name, [])
            current = None
            if sep:
                values.append(value)
            elif name in scalars:
                current, room = values, 1
            elif name not in flags:
                current, room = values, None
        elif current is not None:
            current.append(token)
            if room is not None:
                room -= 1
                if room == 0:
                    current = None
        else:
            _add_positional(result, token)
    _assign_positionals(result, list(positional_names or ()))
    return result


def _add_positional(result, token):
    if token == 'help':
        result.help = True
    else:
        result.positionals.append(token)


def _assign_positionals(result, names):
    if not names:
        return
    for index, token in enumerate(result.positionals):
        name = names[min(index, len(names) - 1)]
        result.positional_values.setdefault(name, []).append(token)
