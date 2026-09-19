# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities for splitting and analysing chained shell commands (&&, ;)."""

import re

from src import shell_syntax

# Matches unquoted && or ; for detection purposes only (use split_chain()
# for actual splitting, which respects quoted strings).
CHAIN_SPLIT_RE = re.compile(r"(?<!['\"])(?:&&|;)(?!['\"])")

# Commands that produce no stdout on success and are safe to ignore
# when determining the "primary" command in a chain.
SILENT_CMDS_RE = re.compile(
    r"^\s*(?:"
    r"cd|pushd|popd"
    r"|mkdir(?:\s+-p)?"
    r"|cp|mv|rm"
    r"|touch|chmod|chown|ln"
    r"|export|unset|source"
    r"|set|shopt|alias|hash|type"
    r"|true|false"
    r"|git\s+(?:add|rm|checkout|switch|reset|clean|config|init|tag|commit"
    r"|mv|restore)"
    r")(?:\s|$)"
)


def split_chain_with_ops(command: str) -> list[tuple[str, str]]:
    """Split unquoted shell chains while retaining each trailing operator.

    Returns a list of ``(segment, operator)`` tuples where operator is ``"&&"``,
    ``";"``, or ``""`` for the final segment.  Quoted strings are respected, so
    ``git commit -m "fix; done"`` is NOT split on the ``;``.

    Args:
        command: Shell text that may contain quoted or chained command segments.

    Returns:
        Ordered (segment, operator) tuples. The final operator is empty.
    """
    result: list[tuple[str, str]] = []
    start = 0
    skip_to = 0

    for i, ch in shell_syntax.iter_unquoted(command):
        if i < skip_to:
            continue  # second '&' of an operator we already consumed
        if ch == "&" and command.startswith("&&", i):
            op, width = "&&", 2
        elif ch == ";":
            op, width = ";", 1
        else:
            continue
        seg = command[start:i].strip()
        if seg:
            result.append((seg, op))
        start = skip_to = i + width

    seg = command[start:].strip()
    if seg:
        result.append((seg, ""))

    return result


def split_chain(command: str) -> list[str]:
    """Split a command string on unquoted ``&&`` and ``;`` into segments.

    Args:
        command: Shell text that may contain quoted or chained command segments.

    Returns:
        Nonempty command segments in their original order.
    """
    return [segment for segment, _ in split_chain_with_ops(command)]


def extract_primary_command(command: str) -> str:
    """Return the last non-silent segment of a (possibly chained) command.

    If no non-silent segment is found, return the last segment.

    Args:
        command: Shell text that may contain quoted or chained command segments.

    Returns:
        Last output-producing segment, or the final segment if all are silent.
    """
    segments = split_chain(command)
    if not segments:
        return command

    # Walk backwards to find the last non-silent segment
    for seg in reversed(segments):
        if not SILENT_CMDS_RE.match(seg):
            return seg

    # All segments are silent — return the last one
    return segments[-1]
