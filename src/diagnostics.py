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

"""Immutable, already-sanitized diagnostic snapshots for local comparisons."""

import dataclasses
import re
import shlex
from typing import Literal

from src import shell_syntax

MAX_DIAGNOSTICS = 500


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    """One actionable problem with its complete captured details.

    Attributes:
        identifier: Stable tool-specific identity, independent of its message.
        summary: Problem description; presentation pairs it with the identifier.
        detail: Exact sanitized primary diagnostic text. Verified redundant
            summary copies may be omitted; unique detail changes stay visible.
    """

    identifier: str
    summary: str
    detail: str


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """Conservative observations from one complete command result.

    Absence from ``diagnostics`` never proves that a previous problem passed.
    Parsers perform no I/O or redaction; callers must sanitize output first.

    Attributes:
        family: Stable format name, such as ``pytest`` or ``ruff``.
        summary: Current run totals, independent of earlier results.
        diagnostics: Problems whose complete detail and identity were parsed.
        passed: Test identities explicitly observed passing in this run.
        context: Other captured text retained verbatim for every presentation,
            except routine pytest headers, verified progress, and summary
            copies already preserved in the primary diagnostic details.
    """

    family: str
    summary: str
    diagnostics: tuple[Diagnostic, ...]
    passed: tuple[str, ...] = ()
    context: str = ""


@dataclasses.dataclass(frozen=True)
class Change:
    """One classified observation in a comparison between complete runs.

    Attributes:
        diagnostic: Current diagnostic, or the prior one when absent now.
        status: Exact comparison outcome. An absent diagnostic is only PASSED
            when the current snapshot explicitly supplies that evidence.
    """

    diagnostic: Diagnostic
    status: Literal["NEW", "CHANGED", "UNCHANGED", "PASSED", "NOT OBSERVED"]

    @property
    def needs_detail(self) -> bool:
        """Whether omitting current detail would lose diagnostic evidence."""
        return self.status in ("NEW", "CHANGED")


def compare(
    snapshot: Snapshot, previous: Snapshot | None = None
) -> tuple[Change, ...]:
    """Classify sanitized observations without formatting or retaining them.

    Identity, summary and full detail must all match to permit elision.
    Current diagnostics retain their order, followed by missing diagnostics
    in prior order. Different command families never form a valid baseline.
    Run summaries and context are independent and remain the caller's
    responsibility to present for every run.

    Args:
        snapshot: Validated observations from the current command execution.
        previous: Validated baseline from the same comparison scope, if any.

    Returns:
        Immutable outcomes shared by presentation and detail-preservation
        decisions. Explicit passes only describe absent prior diagnostics.
    """
    old = {}
    if previous is not None and previous.family == snapshot.family:
        old = {item.identifier: item for item in previous.diagnostics}
    changes = []
    current = set()
    for item in snapshot.diagnostics:
        current.add(item.identifier)
        before = old.get(item.identifier)
        if before == item:
            changes.append(Change(item, "UNCHANGED"))
        elif before is not None:
            changes.append(Change(item, "CHANGED"))
        else:
            changes.append(Change(item, "NEW"))
    for identifier, item in old.items():
        if identifier in current:
            continue
        if identifier in snapshot.passed:
            changes.append(Change(item, "PASSED"))
        else:
            changes.append(Change(item, "NOT OBSERVED"))
    return tuple(changes)


def command_arguments(command: str, names: tuple[str, ...]) -> list[str] | None:
    """Recognize a simple tool invocation and return its arguments.

    Supports executable paths, Python module invocations, and simple ``uv``,
    ``poetry``, and ``pipx run`` launchers. Shell composition and substitutions
    are deliberately unsupported because one snapshot describes one command.

    Args:
        command: Shell command label; it is parsed but never executed.
        names: Exact executable or module names accepted by the caller.

    Returns:
        Arguments after the tool name, or None for an unsupported invocation.
    """
    if shell_syntax.has_unquoted(command, (";", "|", "&", ">", "<", "\n")):
        return None
    if "$" in command or "`" in command:
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if not words:
        return None
    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1]
    if executable in ("uv", "poetry", "pipx"):
        if words[1:2] != ["run"] or len(words) < 3:
            return None
        words = words[2:]
        executable = words[0].replace("\\", "/").rsplit("/", 1)[-1]
    if re.fullmatch(r"python[23]?(?:\.\d+)?(?:\.exe)?", executable):
        if len(words) < 3 or words[1] != "-m" or words[2] not in names:
            return None
        return words[3:]
    if executable.removesuffix(".exe") in names:
        return words[1:]
    return None
