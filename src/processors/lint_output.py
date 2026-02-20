"""Lint output processor: eslint, ruff, flake8, pylint, clippy, rubocop, shellcheck, hadolint."""

import re
from collections import defaultdict

from .. import config
from .base import Processor


class LintOutputProcessor(Processor):
    priority = 27
    hook_patterns = [
        r"^(eslint|ruff(\s+check)?|flake8|pylint|clippy|rubocop|golangci-lint|stylelint|biome\s+(check|lint))\b",
        r"^python3?\s+-m\s+(flake8|pylint|ruff|mypy)\b",
        r"^(mypy|prettier\s+--check|shellcheck|hadolint|tflint|ktlint|swiftlint|cargo\s+clippy)\b",
    ]

    @property
    def name(self) -> str:
        return "lint"

    def can_handle(self, command: str) -> bool:
        return bool(
            re.search(
                r"\b(eslint|ruff(\s+check)?|flake8|pylint|clippy|rubocop|"
                r"golangci-lint|stylelint|prettier\s+--check|biome\s+(check|lint)|"
                r"python3?\s+-m\s+(flake8|pylint|ruff|mypy)|mypy|"
                r"shellcheck|hadolint|tflint|ktlint|swiftlint|cargo\s+clippy)\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()

        violations_by_rule: dict[str, list[str]] = defaultdict(list)
        files_by_rule: dict[str, set[str]] = defaultdict(set)
        ungrouped: list[str] = []
        summary_lines: list[str] = []
        current_file = ""  # Track current file for ESLint block format

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Detect ESLint file header line (path without colon/digits -- not a violation)
            if re.match(r"^/?[\w./_-]+\.\w+$", stripped) and not re.search(r":\d+", stripped):
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

        for rule, violations in sorted(violations_by_rule.items(), key=lambda x: -len(x[1])):
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

        # Include ungrouped lines that might be important (errors, not just noise)
        important_ungrouped = [
            line for line in ungrouped if re.search(r"\b(error|fatal|cannot|failed)\b", line, re.I)
        ]
        if important_ungrouped:
            result.extend(important_ungrouped[:5])

        return "\n".join(result)

    def _parse_violation(self, line: str, current_file: str = "") -> tuple[str, str] | None:
        """Extract (rule_id, filepath) from a lint violation line."""

        # ESLint indented format:  10:5  error  Unexpected var  no-var
        m = re.match(r"^\s*(\d+):(\d+)\s+(error|warning)\s+(.+?)\s{2,}(\S+)\s*$", line)
        if m:
            return m.group(5), current_file

        # ESLint inline: /path/file.js:10:5: 'foo' is not defined. (no-undef)
        m = re.match(r"^(.+?):(\d+):\d+:\s+.+\((\S+)\)\s*$", line)
        if m:
            return m.group(3), m.group(1)

        # ESLint inline alt: /path/file.js:10:5  error  message  rule-name
        m = re.match(r"^(.+?):(\d+):\d+\s+(error|warning)\s+.+?\s{2,}(\S+)\s*$", line)
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
        m = re.match(r"^(.+?):(\d+):\s+(error|warning|note):\s+.+\[(\S+)\]\s*$", line)
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
        m = re.match(r"^(.+?):(\d+):\d+:\s+(warning|error|info|style)\s*-\s*(SC\d+)", line)
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

        return None
