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

"""Summarize test-runner output while retaining failures and totals."""

import re

from src import config
from src import diagnostics
from src.processors import base

_PYTEST_TOTALS = re.compile(
    r"^(?:=+\s*)?(?P<counts>\d+ "
    r"(?:failed|passed|skipped|deselected|xfailed|xpassed|warnings?)"
    r"(?:, \d+ (?:failed|passed|skipped|deselected|"
    r"xfailed|xpassed|warnings?))*)"
    r" in \d+(?:\.\d+)?s(?: \([^\n]+\))?(?:\s*=+)?$"
)
_PYTEST_SECTION = re.compile(r"^=+ .+ =+$")
# Internal traceback frames use spaced single underscores. Only continuous
# underline runs introduce a separate failure, including chained exceptions.
_PYTEST_FAILURE_HEADER = re.compile(r"^_{2,} (.+?) _{2,}$")
_PYTEST_CAPTURED_HEADER = re.compile(
    r"^-+ Captured (?:stdout|stderr|log) (?:setup|call|teardown) -+$"
)
_PYTEST_PROGRESS = re.compile(
    r"^([^\s]+\.py::.+?) (PASSED|FAILED|SKIPPED|XFAIL|XPASS)"
    r"(?: \([^\n]*\))?(?:\s+\[\s*\d+%\])?$"
)


def _pytest_counts(line: str) -> dict[str, int] | None:
    """Read one unambiguous pytest totals line, rejecting duplicate outcomes."""
    match = _PYTEST_TOTALS.fullmatch(line)
    if match is None:
        return None
    counts = {}
    for entry in match["counts"].split(", "):
        count, outcome = entry.split(" ")
        if outcome in counts:
            return None
        counts[outcome] = int(count)
    return counts


def _pytest_progress(
    lines: list[str], counts: dict[str, int]
) -> tuple[tuple[str, ...], set[int]]:
    """Recognize routine headers and passes within clean progress output."""
    in_session = False
    in_progress = False
    passed = []
    headers: set[int] = set()
    progress_lines: set[int] = set()
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if re.fullmatch(r"=+ test session starts =+", line):
            in_session = True
            headers.add(index)
        elif in_session and re.fullmatch(
            r"(?:collecting \.\.\. )?collected \d+ items?(?: / .+)?", line
        ):
            in_progress = True
            headers.add(index)
        elif (
            in_session
            and not in_progress
            and re.fullmatch(
                r"(?:platform .+|(?:rootdir|cachedir|configfile|plugins): .+)",
                line,
            )
        ):
            headers.add(index)
        elif in_progress:
            if _PYTEST_SECTION.fullmatch(line):
                break
            if not line.strip():
                continue
            progress = _PYTEST_PROGRESS.fullmatch(line)
            if progress is None:
                return (), headers
            if progress[2] == "PASSED":
                passed.append(progress[1])
            # Keep skipped/xfail reasons visible even with a complete snapshot.
            if progress[2] in ("PASSED", "FAILED"):
                progress_lines.add(index)
    if len(passed) != counts.get("passed", 0) or len(set(passed)) != len(
        passed
    ):
        return (), headers
    return tuple(passed), headers | progress_lines


def _pytest_detail_stop(lines: list[str], start: int, stop: int) -> int | None:
    """Separate traceback/captured details from unrelated trailing output."""
    footer = None
    for index in range(start + 1, stop):
        if re.fullmatch(r".+\.py:\d+: .+", lines[index].rstrip("\r\n")):
            footer = index
    if footer is None:
        return None
    for index in range(footer + 1, stop):
        if _PYTEST_CAPTURED_HEADER.fullmatch(lines[index].rstrip("\r\n")):
            return stop
    return footer + 1


def _pytest_summary_pattern(titles: list[str]) -> re.Pattern[str]:
    """Use observed failure titles to disambiguate summary message separators.

    Parameter IDs can contain `` - `` themselves. Matching complete node names
    against the full failure headers prevents splitting such IDs at their first
    apparent message separator. Pytest displays class separators as dots only
    before the parameter portion of its failure headers.
    """
    names = []
    for title in titles:
        before_params, bracket, parameters = title.partition("[")
        name = before_params.replace(".", "::") + bracket + parameters
        names.append(re.escape(name))
    return re.compile(
        r"^FAILED (.+?\.py::(?:" + "|".join(names) + r"))(?: - (.*))?$"
    )


def _pytest_summary_end(
    lines: list[str], start: int, summary: str, detail: str
) -> int:
    """Locate only a complete redundant exception message in the short summary.

    Verbose pytest output repeats multiline assertion messages and full diffs
    in the short summary. A continuation duplicates the failure only when it
    exactly matches a complete ``E`` block from that failure's traceback, with
    pytest's common prefix removed. Partial matches and unknown text remain
    context. The original traceback remains verbatim in the diagnostic detail;
    captured application output is never evidence for this match.
    """
    detail_lines = detail.splitlines()
    index = 0
    while index < len(detail_lines):
        line = detail_lines[index]
        if _PYTEST_CAPTURED_HEADER.fullmatch(line):
            break
        message = re.fullmatch(r"E( +)(\S.*)", line)
        index += 1
        if message is None:
            continue
        prefix = "E" + message[1]
        continuation = []
        while index < len(detail_lines) and detail_lines[index].startswith(
            prefix
        ):
            continuation.append(detail_lines[index][len(prefix) :])
            index += 1
        if message[2] != summary or not continuation:
            continue
        stop = start + 1 + len(continuation)
        captured = [line.rstrip("\r\n") for line in lines[start + 1 : stop]]
        if captured == continuation:
            return stop
    return start + 1


def _pytest_failure_diagnostics(
    lines: list[str], failed: int
) -> tuple[tuple[diagnostics.Diagnostic, ...], set[int]] | None:
    """Match every short-summary identity to exactly one full failure block."""
    sections = []
    short_sections = []
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if re.fullmatch(r"=+ FAILURES =+", line):
            sections.append(index)
        elif re.fullmatch(r"=+ short test summary info =+", line):
            short_sections.append(index)
    if len(sections) != 1 or len(short_sections) != 1:
        return None
    start, short = sections[0], short_sections[0]
    if start >= short:
        return None
    end = short
    for index in range(start + 1, short):
        if _PYTEST_SECTION.fullmatch(lines[index].rstrip("\r\n")):
            end = index
            break
    headers = []
    for index in range(start + 1, end):
        match = _PYTEST_FAILURE_HEADER.fullmatch(lines[index].rstrip("\r\n"))
        if match:
            headers.append((index, match[1]))
    if len(headers) != failed:
        return None
    summary_pattern = _pytest_summary_pattern([title for _, title in headers])
    identities = {}
    consumed = {start, short}
    for index in range(short + 1, len(lines)):
        line = lines[index].rstrip("\r\n")
        if _PYTEST_SECTION.fullmatch(line) or _pytest_counts(line) is not None:
            break
        match = summary_pattern.fullmatch(line)
        if match is None:
            if line.startswith("FAILED "):
                return None
            continue
        identifier = match[1]
        before_params, bracket, parameters = identifier.partition("[")
        title = ".".join(before_params.split("::")[1:])
        title += bracket + parameters
        if title in identities:
            return None
        identities[title] = (identifier, match[2] or "failed", index)
    if len(identities) != failed:
        return None
    result = []
    seen = set()
    for position, (index, title) in enumerate(headers):
        if title not in identities or title in seen:
            return None
        seen.add(title)
        stop = headers[position + 1][0] if position + 1 < failed else end
        detail_stop = _pytest_detail_stop(lines, index, stop)
        if detail_stop is None:
            return None
        stop = detail_stop
        detail = "".join(lines[index:stop])
        # A header alone is not evidence that a traceback was captured.
        if not re.search(r"(?m)^(?:E\s+|[^\n]+\.py:\d+: )", detail):
            return None
        identifier, summary, summary_index = identities[title]
        test_path = re.escape(identifier.partition("::")[0])
        if not re.search(rf"(?m)^{test_path}:\d+:", detail):
            return None
        summary_stop = _pytest_summary_end(
            lines, summary_index, summary, detail
        )
        result.append(diagnostics.Diagnostic(identifier, summary, detail))
        consumed.update(range(index, stop))
        consumed.update(range(summary_index, summary_stop))
    return tuple(result), consumed


def _pytest_snapshot(
    command: str, output: str, exit_code: int | None
) -> diagnostics.Snapshot | None:
    """Parse complete ordinary pytest runs, retaining all unrelated context."""
    arguments = diagnostics.command_arguments(command, ("pytest", "py.test"))
    if arguments is None or exit_code not in (None, 0, 1):
        return None
    if any(
        argument.startswith(("--tb", "--capture", "--collect", "--setup"))
        for argument in arguments
    ) or any(
        argument == "--no-summary" or re.fullmatch(r"-[^-]*s[^-]*", argument)
        for argument in arguments
    ):
        return None
    if re.search(
        r"(?im)(?:^=+ (?:ERRORS|.*interrupted.*) =+$|^INTERNALERROR|"
        r"^!+|\b(?:output|traceback) (?:truncated|omitted)\b)",
        output,
    ):
        return None
    lines = output.splitlines(keepends=True)
    totals = []
    for index, line in enumerate(lines):
        counts = _pytest_counts(line.rstrip("\r\n"))
        if counts is not None:
            totals.append((index, counts))
    if len(totals) != 1:
        return None
    total_index, counts = totals[0]
    failed = counts.get("failed", 0)
    if failed > diagnostics.MAX_DIAGNOSTICS:
        return None
    if (exit_code == 0 and failed) or (exit_code == 1 and not failed):
        return None
    parsed: tuple[diagnostics.Diagnostic, ...] = ()
    consumed: set[int] = set()
    if failed:
        result = _pytest_failure_diagnostics(lines[:total_index], failed)
        if result is None:
            return None
        parsed, consumed = result
    elif any(
        "FAILURES" in line or line.startswith("FAILED ") for line in lines
    ):
        return None
    consumed.add(total_index)
    passed, routine_lines = _pytest_progress(lines[:total_index], counts)
    # Repeated collection or retries can report both outcomes for one node.
    # A snapshot needs one unambiguous state per identity to remain readable.
    if any(item.identifier in passed for item in parsed):
        return None
    consumed.update(routine_lines)
    context = "".join(line for i, line in enumerate(lines) if i not in consumed)
    return diagnostics.Snapshot(
        family="pytest",
        summary=lines[total_index].strip("= \r\n"),
        diagnostics=parsed,
        passed=passed,
        context=context,
    )


class TestOutputProcessor(base.Processor):
    """Summarize test runs while retaining failure blocks and totals."""

    priority = 21
    handles_failure = True
    hook_patterns = [
        (
            rf"^(pytest|py\.test|{base.PYTHON_CMD}\s+-m\s+pytest|jest|mocha|"
            rf"vitest|cargo\s+test|go\s+test|rspec|phpunit|bun\s+test|"
            rf"dotnet\s+test|swift\s+test|mix\s+test)\b"
        ),
        r"^(npm\s+test|yarn\s+test|pnpm\s+test)\b",
        (
            r"^(npx\s+(jest|mocha|vitest|playwright)\b|poetry\s+run\s+(pytest|"
            r"py\.test)\b|uv\s+run\s+(pytest|py\.test)\b|pipx\s+run\s+pytest\b|"
            r"bundle\s+exec\s+(rspec|rails\s+test)\b)"
        ),
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "test"

    def diagnostics(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> diagnostics.Snapshot | None:
        """Describe complete pytest failures without shortening their details.

        Args:
            command: Simple pytest invocation, including supported launchers.
            output: Complete, already-sanitized captured output.
            exit_code: Actual command status, if known.

        Returns:
            A snapshot retaining warnings and unknown text, or None for
            unsupported tools, ambiguous identities, or incomplete output.
        """
        return _pytest_snapshot(command, output, exit_code)

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(
            re.search(
                rf"\b(pytest|py\.test|{base.PYTHON_CMD}\s+-m\s+pytest|"
                r"jest|mocha|"
                r"cargo\s+test|go\s+test|rspec|phpunit|vitest|bun\s+test|"
                r"npm\s+test|yarn\s+test|pnpm\s+test|"
                r"dotnet\s+test|swift\s+test|mix\s+test|"
                r"npx\s+(jest|mocha|vitest|playwright)|"
                r"poetry\s+run\s+(pytest|py\.test)|uv\s+run\s+(pytest|"
                r"py\.test)|"
                r"pipx\s+run\s+pytest|bundle\s+exec\s+(rspec|rails\s+test))\b",
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

        if re.search(
            rf"\bpytest\b|py\.test|{base.PYTHON_CMD}\s+-m\s+pytest"
            r"|\b(poetry|uv|pipx)\s+run\s+pytest",
            command,
        ):
            return self._process_pytest(lines)
        if re.search(
            r"\bjest\b|\bvitest\b|\bnpm\s+test\b|\byarn\s+test\b"
            r"|\bpnpm\s+test\b|\bnpx\s+(jest|vitest)\b",
            command,
        ):
            return self._process_jest(lines)
        if re.search(r"\bcargo\s+test\b", command):
            return self._process_cargo_test(lines)
        if re.search(r"\bgo\s+test\b", command):
            return self._process_go_test(lines)
        if re.search(r"\brspec\b|\bbundle\s+exec\s+rspec\b", command):
            return self._process_rspec(lines)
        if re.search(r"\bdotnet\s+test\b", command):
            return self._process_dotnet_test(lines)
        if re.search(r"\bswift\s+test\b", command):
            return self._process_swift_test(lines)
        if re.search(r"\bmix\s+test\b", command):
            return self._process_mix_test(lines)
        return self._process_generic_test(lines)

    def _truncate_traceback(self, block: list[str]) -> list[str]:
        """Truncate a failure/traceback block to max_traceback_lines."""
        max_lines = config.get("max_traceback_lines")
        if len(block) <= max_lines:
            return block
        # Keep first half and last half, insert truncation marker
        keep_head = max_lines // 2
        keep_tail = max_lines - keep_head
        omitted = len(block) - keep_head - keep_tail
        return [
            *block[:keep_head],
            f"    ... ({omitted} traceback lines truncated)",
            *block[-keep_tail:],
        ]

    def _process_pytest(self, lines: list[str]) -> str:
        """Retain pytest failures and totals while summarizing passes."""
        result = []
        in_failure = False
        in_warnings = False
        failure_block: list[str] = []
        warning_lines: list[str] = []
        summary_lines = []
        passed_count = 0
        param_tests: dict[
            str, dict
        ] = {}  # base_name -> {"passed": int, "failed": [param]}

        for line in lines:
            # Skip collection output
            if re.match(r"^(collecting|collected)\s", line.strip()):
                continue
            # Skip platform/rootdir/configfile lines
            if re.match(
                r"^(platform|rootdir|configfile|plugins|cachedir)[\s:]",
                line.strip(),
            ):
                continue

            # Detect FAILURES section
            if re.match(r"^=+ FAILURES =+", line):
                in_failure = True
                in_warnings = False
                result.append(line)
                continue

            # Detect warnings summary section
            if re.match(r"^=+ warnings summary =+", line):
                in_warnings = True
                in_failure = False
                if failure_block:
                    result.extend(self._truncate_traceback(failure_block))
                    failure_block = []
                continue

            if in_warnings:
                # End of warnings section
                if re.match(r"^=+.*=+$", line):
                    in_warnings = False
                    # Collapse warnings by type
                    if warning_lines:
                        result.extend(self._collapse_warnings(warning_lines))
                        warning_lines = []
                    summary_lines.append(line)
                else:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("--"):
                        warning_lines.append(stripped)
                continue

            if in_failure:
                # New test failure header within FAILURES section
                if re.match(r"^_+ .+ _+$", line):
                    # Flush previous failure block
                    if failure_block:
                        result.extend(self._truncate_traceback(failure_block))
                        failure_block = []
                    result.append(line)
                    continue

                # End of failures block
                if re.match(
                    (
                        r"^=+ (short test summary|warnings summary|\d+ (failed|"
                        r"passed|error))"
                    ),
                    line,
                ):
                    in_failure = False
                    if failure_block:
                        result.extend(self._truncate_traceback(failure_block))
                        failure_block = []
                    if "warnings summary" in line:
                        in_warnings = True
                    else:
                        result.append(line)
                elif re.match(r"^=+.*=+$", line) and "FAILURES" not in line:
                    in_failure = False
                    if failure_block:
                        result.extend(self._truncate_traceback(failure_block))
                        failure_block = []
                    result.append(line)
                else:
                    failure_block.append(line)
                continue

            # Count passed tests
            if re.search(r"\bPASSED\b", line):
                passed_count += 1
                # Track parameterized tests
                m = re.match(r"^(\S+?)\[(.+)\]\s+PASSED", line.strip())
                if m:
                    test_name = m.group(1)
                    param_tests.setdefault(
                        test_name, {"passed": 0, "failed": []}
                    )
                    param_tests[test_name]["passed"] += 1
                continue

            # Keep FAILED/ERROR individual lines
            if re.search(r"\bFAILED\b|\bERROR\b", line):
                # Track parameterized test failures
                m = re.match(r"^(\S+?)\[(.+)\]\s+FAILED", line.strip())
                if m:
                    test_name = m.group(1)
                    param = m.group(2)
                    param_tests.setdefault(
                        test_name, {"passed": 0, "failed": []}
                    )
                    param_tests[test_name]["failed"].append(param)
                else:
                    result.append(line)
                continue

            # Keep final summary lines (skip "test session starts" header)
            if (
                re.match(r"^=+.*=+$", line)
                and "test session starts" not in line
            ):
                summary_lines.append(line)
                continue

            # Keep short test summary section lines
            if re.match(r"^(FAILED|ERROR)\s", line.strip()):
                result.append(line)

        # Handle unclosed warnings section
        if warning_lines:
            result.extend(self._collapse_warnings(warning_lines))
        # Handle unclosed failure block
        if failure_block:
            result.extend(self._truncate_traceback(failure_block))

        # Add grouped summaries for parameterized tests with failures
        for test_name, info in param_tests.items():
            if info["failed"]:
                total = info["passed"] + len(info["failed"])
                failed_params = ", ".join(info["failed"][:5])
                extra = ""
                if len(info["failed"]) > 5:
                    extra = f", ... ({len(info['failed']) - 5} more)"
                result.append(
                    f"{test_name}: {info['passed']}/{total} passed, FAILED: "
                    f"[{failed_params}{extra}]"
                )

        if passed_count > 0:
            result.insert(0, f"[{passed_count} tests passed]")

        # Detect and compress coverage report in remaining lines
        coverage_lines = self._extract_coverage(lines)
        if coverage_lines:
            result.extend(self._compress_coverage(coverage_lines))

        result.extend(summary_lines)
        return "\n".join(result) if result else "\n".join(lines)

    def _extract_coverage(self, lines: list[str]) -> list[str]:
        """Extract coverage table lines from pytest output."""
        coverage_start = None
        coverage_end = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if coverage_start is None and (
                re.match(r"^-+ coverage", stripped)
                or re.match(r"^Name\s+Stmts\s+Miss", stripped)
            ):
                coverage_start = i
            if (
                coverage_start is not None
                and i > coverage_start
                and re.match(r"^TOTAL\s+", stripped)
            ):
                coverage_end = i
                break
        if coverage_start is None:
            return []
        end = coverage_end + 1 if coverage_end is not None else len(lines)
        return lines[coverage_start:end]

    def _compress_coverage(self, lines: list[str]) -> list[str]:
        """Compress pytest coverage report: keep low-coverage files + TOTAL."""
        result = []
        total_line = ""
        low_coverage_files = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("TOTAL"):
                total_line = stripped
                continue
            if stripped.startswith(("Name", "-")):
                continue
            # Parse: filename  stmts  miss  cover%
            m = re.match(r"^(\S+)\s+\d+\s+\d+\s+(\d+)%", stripped)
            if m:
                cover_pct = int(m.group(2))
                if cover_pct < 80:
                    low_coverage_files.append(stripped)

        if total_line:
            result.append(total_line)
        if low_coverage_files:
            result.append(
                f"Files below 80% coverage ({len(low_coverage_files)}):"
            )
            for f in low_coverage_files[:10]:
                result.append(f"  {f}")
            if len(low_coverage_files) > 10:
                result.append(f"  ... ({len(low_coverage_files) - 10} more)")

        return result

    def _collapse_warnings(self, warning_lines: list[str]) -> list[str]:
        """Group warnings by type, show count + one example per type."""
        by_type: dict[str, list[str]] = {}
        for line in warning_lines:
            # Extract warning type: "DeprecationWarning: ...", "UserWarning:
            # ...", etc.
            m = re.search(r"(\w+Warning):\s*(.+)", line)
            if m:
                wtype = m.group(1)
                by_type.setdefault(wtype, []).append(line)
            elif re.match(r"^\s*/", line) or re.match(r"^\s+\w+", line):
                # Source location lines -- associate with last warning type
                continue
            else:
                by_type.setdefault("other", []).append(line)

        if not by_type:
            return []

        result = []
        total = sum(len(v) for v in by_type.values())
        parts = []
        for wtype, instances in sorted(
            by_type.items(), key=lambda x: -len(x[1])
        ):
            if wtype == "other":
                continue
            parts.append(f"{wtype} x{len(instances)}")
        if parts:
            result.append(f"Warnings ({total}): {', '.join(parts)}")
            # Show one example from the most common type
            most_common = max(by_type.items(), key=lambda x: len(x[1]))
            if most_common[1]:
                result.append(f"  e.g. {most_common[1][0]}")
        return result

    def _process_jest(self, lines: list[str]) -> str:
        """Retain Jest failure blocks and summary counts, collapsing passes."""
        result = []
        in_failure = False
        passed_suites = 0
        passed_tests = 0
        failure_buffer: list[str] = []
        consecutive_blanks = 0

        for line in lines:
            stripped = line.strip()

            # Capture failure blocks
            if re.search(r"\bFAIL\b", line) and not re.match(
                r"^(Tests?|Test Suites?):", stripped
            ):
                in_failure = True
                consecutive_blanks = 0
                result.append(line)
                continue

            if in_failure:
                failure_buffer.append(line)
                if not stripped:
                    consecutive_blanks += 1
                    # End of failure block after 2 consecutive blank lines
                    if consecutive_blanks >= 2:
                        result.extend(self._truncate_traceback(failure_buffer))
                        failure_buffer = []
                        in_failure = False
                        consecutive_blanks = 0
                else:
                    consecutive_blanks = 0
                continue

            if re.search(r"\bPASS\b", line) and not re.match(
                r"^(Tests?|Test Suites?):", stripped
            ):
                passed_suites += 1
                m = re.search(r"\((\d+)\s+tests?\)", line)
                if m:
                    passed_tests += int(m.group(1))
                continue

            # Keep summary lines
            if re.match(
                r"^(Tests?|Test Suites?|Snapshots?|Time|Ran all):", stripped
            ):
                result.append(line)

        if failure_buffer:
            result.extend(self._truncate_traceback(failure_buffer))

        if passed_suites > 0:
            result.insert(0, f"[{passed_suites} suites passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_cargo_test(self, lines: list[str]) -> str:
        """Retain Rust test failures and totals while counting passing tests."""
        result = []
        in_failure = False
        ok_count = 0

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("test ") and "... ok" in stripped:
                ok_count += 1
                continue

            if "FAILED" in stripped:
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                # End on blank or test result line
                if stripped.startswith("test result:"):
                    in_failure = False
                continue

            if stripped.startswith("test result:"):
                result.append(line)
                continue

            # Skip compilation output
            if re.match(
                r"^\s*(Compiling|Downloading|Running|Doc-tests)", stripped
            ):
                continue

        if ok_count > 0:
            result.insert(0, f"[{ok_count} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_go_test(self, lines: list[str]) -> str:
        """Retain Go test failures and package summaries, collapsing passes."""
        result = []
        passed = 0
        in_failure = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("--- PASS"):
                passed += 1
                continue

            if stripped.startswith("--- FAIL"):
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                if re.match(r"^(FAIL|ok)\s+\S+", stripped):
                    in_failure = False
                continue

            # Package summary lines
            if re.match(r"^(ok|FAIL)\s+\S+", stripped):
                result.append(line)
                continue

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_rspec(self, lines: list[str]) -> str:
        """Retain RSpec failures and totals while removing progress dots."""
        result = []
        passed = 0
        in_failure = False

        for line in lines:
            stripped = line.strip()

            if re.match(r"^\d+ examples?, \d+ failures?", stripped):
                result.append(line)
                continue

            if "FAILED" in stripped or "Failure/Error" in stripped:
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                if not stripped:
                    in_failure = False
                continue

            # Dots-only progress line: count only dots, not other chars
            if re.match(r"^[.FE*P]+$", stripped):
                passed += stripped.count(".")
                continue

            # Checkmark lines
            if re.match(r"^\s*(✓|✔)", stripped):
                passed += 1
                continue

        if passed > 0:
            result.insert(0, f"[{passed} examples passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_dotnet_test(self, lines: list[str]) -> str:
        """Compress dotnet test output."""
        result = []
        passed = 0
        in_failure = False

        for line in lines:
            stripped = line.strip()

            # Skip build output
            if re.match(r"^\s*(Build|Restore|Determining|Microsoft)", stripped):
                continue

            if (
                stripped.startswith("Passed!")
                or re.search(r"\bPassed\b", stripped)
            ) and "test" not in stripped.lower():
                passed += 1
                continue

            if re.search(r"\bFailed\b", stripped):
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                if not stripped or re.match(
                    r"^(Total|Passed|Failed|Skipped)\s", stripped
                ):
                    in_failure = False
                continue

            # Summary lines
            if re.match(
                r"^(Total tests|Passed|Failed|Skipped|Test Run)", stripped
            ):
                result.append(line)

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_swift_test(self, lines: list[str]) -> str:
        """Compress swift test output."""
        result = []
        passed = 0

        for line in lines:
            stripped = line.strip()

            # Skip build/compile lines
            if re.match(r"^\s*(Build|Compile|Link|Fetch|Creating)", stripped):
                continue

            if "passed" in stripped.lower() and "test" not in stripped.lower():
                passed += 1
                continue

            if re.search(r"\bfailed\b|\bFailed\b|\berror\b", stripped):
                result.append(line)
                continue

            # Test suite summary
            if re.match(r"^Test Suite", stripped) or re.match(
                r"^Executed \d+", stripped
            ):
                result.append(line)

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_mix_test(self, lines: list[str]) -> str:
        """Compress Elixir mix test output."""
        result = []
        passed = 0
        in_failure = False

        for line in lines:
            stripped = line.strip()

            # Skip compilation
            if re.match(r"^\s*(Compiling|Generated)\s", stripped):
                continue

            # Dots progress line
            if re.match(r"^\.+$", stripped):
                passed += len(stripped)
                continue

            if re.search(r"\bfailure\b|\bFailed\b", stripped, re.IGNORECASE):
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                if not stripped:
                    in_failure = False
                continue

            # Summary line
            if re.match(r"^\d+\s+(tests?|doctests?)", stripped):
                result.append(line)

            # Finished line
            if re.match(r"^Finished in", stripped):
                result.append(line)

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_generic_test(self, lines: list[str]) -> str:
        """Retain recognized failure context and test summary lines."""
        result = []
        passed = 0

        for line in lines:
            lower = line.lower()
            if any(
                kw in lower
                for kw in ["fail", "error", "assert", "exception", "traceback"]
            ):
                result.append(line)
            elif any(
                kw in lower for kw in ["pass", "ok ", "success"]
            ) or re.match(r"^\s*(✓|✔)", line.strip()):
                passed += 1
            elif re.match(r"^\d+\s+(tests?|specs?|examples?)", line.strip()):
                result.append(line)

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines[-10:])
