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

"""Group lint-tool diagnostics by rule and retain example locations."""

import collections
import re

from src import config
from src import diagnostics
from src.processors import base

_RUFF_LOCATION = re.compile(r"^(.+?):([1-9]\d*):([1-9]\d*): ([A-Z]+\d+) (.+)$")
_RUFF_HEADER = re.compile(r"^([A-Z]+\d+) (.+)$")
_RUFF_ARROW = re.compile(r"^\s*--> (.+?):([1-9]\d*):([1-9]\d*)$")


def _ruff_arguments(command: str) -> bool:
    """Limit snapshots to non-mutating checks in supported text formats."""
    arguments = diagnostics.command_arguments(command, ("ruff",))
    if arguments is None or arguments[:1] != ["check"]:
        return False
    for index, argument in enumerate(arguments[1:], start=1):
        if argument.startswith(
            (
                "--fix",
                "--unsafe-fixes",
                "--diff",
                "--watch",
                "--statistics",
                "--show",
                "--exit-zero",
                "--output-file",
            )
        ) or argument in ("-w", "--quiet", "-q", "-o"):
            return False
        if argument == "--output-format":
            if arguments[index + 1 : index + 2] not in (["full"], ["concise"]):
                return False
        elif argument.startswith("--output-format=") and argument.partition(
            "="
        )[2] not in ("full", "concise"):
            return False
    return True


def _ruff_detail_end(lines: list[str], start: int) -> int:
    """Consume source gutters and help, leaving unknown tool text as context."""
    stop = start
    while stop < len(lines):
        line = lines[stop].rstrip("\r\n")
        if (
            not line.strip()
            or re.fullmatch(r"\s*(?:\d+\s*)?\|.*", line)
            or line.startswith("help: ")
        ):
            stop += 1
        else:
            break
    return stop


def _ruff_snapshot(
    command: str, output: str, exit_code: int | None
) -> diagnostics.Snapshot | None:
    """Parse default full or concise Ruff diagnostics with verified totals."""
    if not _ruff_arguments(command) or exit_code not in (None, 0, 1):
        return None
    lines = output.splitlines(keepends=True)
    result: list[diagnostics.Diagnostic] = []
    consumed: set[int] = set()
    identifiers: set[str] = set()
    summaries = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r\n")
        total = re.fullmatch(r"Found (\d+) errors?\.", line)
        if total or line == "All checks passed!":
            summaries.append((index, int(total[1]) if total else 0))
            index += 1
            continue
        location = _RUFF_LOCATION.fullmatch(line)
        header = _RUFF_HEADER.fullmatch(line)
        detail_start = index + 1
        if location:
            path, row, column, rule, message = location.groups()
        elif header and index + 1 < len(lines):
            arrow = _RUFF_ARROW.fullmatch(lines[index + 1].rstrip("\r\n"))
            if arrow is None:
                return None
            path, row, column = arrow.groups()
            rule, message = header.groups()
            detail_start = index + 2
        else:
            index += 1
            continue
        identifier = f"{path}:{row}:{column}:{rule}"
        if (
            identifier in identifiers
            or len(result) >= diagnostics.MAX_DIAGNOSTICS
        ):
            return None
        identifiers.add(identifier)
        stop = _ruff_detail_end(lines, detail_start)
        result.append(
            diagnostics.Diagnostic(
                identifier,
                f"{rule} {message}",
                "".join(lines[index:stop]),
            )
        )
        consumed.update(range(index, stop))
        index = stop
    if len(summaries) != 1:
        return None
    summary_index, count = summaries[0]
    if count != len(result) or (exit_code == 0 and count):
        return None
    if exit_code == 1 and not count:
        return None
    # Diagnostics after the total indicate concatenated or malformed output.
    if any(index > summary_index for index in consumed):
        return None
    consumed.add(summary_index)
    context = "".join(line for i, line in enumerate(lines) if i not in consumed)
    return diagnostics.Snapshot(
        family="ruff",
        summary=lines[summary_index].rstrip("\r\n"),
        diagnostics=tuple(result),
        context=context,
    )


class LintOutputProcessor(base.Processor):
    """Group lint violations by rule while retaining example locations."""

    priority = 27
    handles_failure = True
    hook_patterns = [
        (
            r"^(eslint|ruff(\s+check)?|flake8|pylint|rubocop|golangci-lint|"
            r"stylelint|biome\s+(check|lint))\b"
        ),
        rf"^{base.PYTHON_CMD}\s+-m\s+(flake8|pylint|ruff|mypy)\b",
        (
            r"^(mypy|prettier\s+--check|shellcheck|hadolint|tflint|ktlint|"
            r"swiftlint)\b"
        ),
        r"^(oxlint|deno\s+lint)\b",
        (
            r"^(npx\s+(eslint|prettier|stylelint|biome)\b|"
            r"poetry\s+run\s+(flake8|pylint|ruff|mypy)\b|uv\s+run\s+(flake8|"
            r"pylint|ruff|mypy|ruff\s+check)\b|bundle\s+exec\s+rubocop\b)"
        ),
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "lint"

    def diagnostics(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> diagnostics.Snapshot | None:
        """Describe complete Ruff check results in supported text formats.

        Args:
            command: Simple, non-mutating Ruff check invocation.
            output: Complete, already-sanitized captured output.
            exit_code: Actual command status, if known.

        Returns:
            A snapshot preserving full details and unrelated text, or None
            when the format, count, identities, or completion is uncertain.
        """
        return _ruff_snapshot(command, output, exit_code)

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(
            re.search(
                r"\b(eslint|ruff(\s+check)?|flake8|pylint|clippy|rubocop|"
                r"golangci-lint|stylelint|prettier\s+--check|biome\s+(check|"
                r"lint)|"
                rf"{base.PYTHON_CMD}\s+-m\s+(flake8|pylint|ruff|mypy)|mypy|"
                r"shellcheck|hadolint|tflint|ktlint|swiftlint|cargo\s+clippy|"
                r"oxlint|deno\s+lint|"
                r"npx\s+(eslint|prettier|stylelint|biome)|"
                r"poetry\s+run\s+(flake8|pylint|ruff|mypy)|"
                r"uv\s+run\s+(flake8|pylint|ruff|mypy|ruff\s+check)|"
                r"bundle\s+exec\s+rubocop)\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
        """Compress captured output according to this processor's rules.

        Args:
            command: Original shell command used to select output handling.
            output: Captured command output before this transformation.

        Returns:
            Compressed text, or the input when no safe reduction is available.
        """
        if not output or not output.strip():
            return output

        lines = output.splitlines()

        violations_by_rule: dict[str, list[str]] = collections.defaultdict(list)
        files_by_rule: dict[str, set[str]] = collections.defaultdict(set)
        ungrouped: list[str] = []
        summary_lines: list[str] = []
        current_file = ""  # Track current file for ESLint block format

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Detect ESLint file header line (path without colon/digits -- not a
            # violation)
            if re.match(r"^/?[\w./_-]+\.\w+$", stripped) and not re.search(
                r":\d+", stripped
            ):
                current_file = stripped
                continue

            parsed = self._parse_violation(stripped, current_file)
            if parsed:
                rule, filepath = parsed
                violations_by_rule[rule].append(stripped)
                if filepath:
                    files_by_rule[rule].add(filepath)
            elif (
                re.match(r"^\s*\d+\s+(error|warning|problem)", stripped)
                or re.search(r"(Found|Total|All checks)\s+\d+", stripped)
                or re.match(r"^(error|warning):", stripped.lower())
                or re.match(r"^\s*✖\s+\d+\s+problem", stripped)
            ):
                summary_lines.append(stripped)
            else:
                ungrouped.append(stripped)

        if not violations_by_rule:
            return output

        example_count = config.get("lint_example_count")
        group_threshold = config.get("lint_group_threshold")

        result = []
        total_violations = sum(len(v) for v in violations_by_rule.values())
        total_rules = len(violations_by_rule)
        result.append(f"{total_violations} issues across {total_rules} rules:")

        for rule, violations in sorted(
            violations_by_rule.items(), key=lambda x: -len(x[1])
        ):
            count = len(violations)
            file_count = len(files_by_rule[rule])
            if count > group_threshold:
                loc = f" in {file_count} files" if file_count > 1 else ""
                result.append(f"  {rule}: {count} occurrences{loc}")
                for v in violations[:example_count]:
                    result.append(f"    {v}")
                if count > example_count:
                    result.append(f"    ... ({count - example_count} more)")
            else:
                for v in violations:
                    result.append(f"  {v}")

        if summary_lines:
            result.extend(summary_lines)

        # Include ungrouped lines that might be important (errors, not just
        # noise)
        important_ungrouped = [
            line
            for line in ungrouped
            if re.search(r"\b(error|fatal|cannot|failed)\b", line, re.I)
        ]
        if important_ungrouped:
            result.extend(important_ungrouped[:5])

        return "\n".join(result)

    def _parse_violation(
        self, line: str, current_file: str = ""
    ) -> tuple[str, str] | None:
        """Extract (rule_id, filepath) from a lint violation line."""
        # ESLint indented format:  10:5  error  Unexpected var  no-var
        m = re.match(
            r"^\s*(\d+):(\d+)\s+(error|warning)\s+(.+?)\s{2,}(\S+)\s*$", line
        )
        if m:
            return m.group(5), current_file

        # ESLint inline: /path/file.js:10:5: 'foo' is not defined. (no-undef)
        m = re.match(r"^(.+?):(\d+):\d+:\s+.+\((\S+)\)\s*$", line)
        if m:
            return m.group(3), m.group(1)

        # ESLint inline alt: /path/file.js:10:5  error  message  rule-name
        m = re.match(
            r"^(.+?):(\d+):\d+\s+(error|warning)\s+.+?\s{2,}(\S+)\s*$", line
        )
        if m:
            return m.group(4), m.group(1)

        # Ruff/Flake8: path/file.py:10:5: E501 line too long
        m = re.match(r"^(.+?):(\d+):\d+:\s+([A-Z]\w?\d+)\s+", line)
        if m:
            return m.group(3), m.group(1)

        # Pylint: path/file.py:10:0: C0114: message (rule-name)
        m = re.match(r"^(.+?):(\d+):\d+:\s+\w+:\s+.+\((\S+)\)\s*$", line)
        if m:
            return m.group(3), m.group(1)

        # mypy: file.py:10: error: message  [error-code]
        m = re.match(
            r"^(.+?):(\d+):\s+(error|warning|note):\s+.+\[(\S+)\]\s*$", line
        )
        if m:
            return m.group(4), m.group(1)

        # Clippy: warning[rule]: message
        m = re.match(r"^(warning|error)\[(\S+)\]", line)
        if m:
            return m.group(2), ""

        # Clippy/Rust fallback: warning: message [rule-name]
        # Exclude summary brackets like [1 warning], [3 errors]
        m = re.search(r"\[([a-z][a-z0-9_-]+)\]\s*$", line)
        if m and re.match(r"^(warning|error):", line):
            return m.group(1), ""

        # shellcheck: In file.sh line N: SC2086 ...
        m = re.match(r"^In (.+?) line (\d+):", line)
        if m:
            return "shellcheck", m.group(1)
        m = re.match(
            r"^(.+?):(\d+):\d+:\s+(warning|error|info|style)\s*-\s*(SC\d+)",
            line,
        )
        if m:
            return m.group(4), m.group(1)

        # hadolint: file:line DL3008 ...
        m = re.match(r"^(.+?):(\d+)\s+(DL\d+|SC\d+)\s+", line)
        if m:
            return m.group(3), m.group(1)

        # biome: file.ts:10:5 lint/rule message
        m = re.match(r"^(.+?):(\d+):\d+\s+(lint/\S+)\s+", line)
        if m:
            return m.group(3), m.group(1)

        # golangci-lint: file.go:10:5: message (linter-name)
        m = re.match(
            r"^(.+?\.go):(\d+):\d+:\s+.+\(([a-zA-Z][\w-]*)\)\s*$", line
        )
        if m:
            return m.group(3), m.group(1)

        # rubocop: file.rb:10:5: C: Rule/Name: message
        m = re.match(r"^(.+?\.rb):(\d+):\d+:\s+[CWEFR]:\s+(\S+?):\s+", line)
        if m:
            return m.group(3), m.group(1)

        return None
