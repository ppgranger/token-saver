"""Test runner output processor: pytest, jest, mocha, cargo test, go test, rspec, dotnet test."""

import re

from .. import config
from .base import PYTHON_CMD, Processor


class TestOutputProcessor(Processor):
    priority = 21
    hook_patterns = [
        rf"^(pytest|py\.test|{PYTHON_CMD}\s+-m\s+pytest|jest|mocha|vitest|cargo\s+test|go\s+test|rspec|phpunit|bun\s+test|dotnet\s+test|swift\s+test|mix\s+test)\b",
        r"^(npm\s+test|yarn\s+test|pnpm\s+test)\b",
        r"^(npx\s+(jest|mocha|vitest|playwright)\b|poetry\s+run\s+(pytest|py\.test)\b|uv\s+run\s+(pytest|py\.test)\b|pipx\s+run\s+pytest\b|bundle\s+exec\s+(rspec|rails\s+test)\b)",
    ]

    @property
    def name(self) -> str:
        return "test"

    def can_handle(self, command: str) -> bool:
        return bool(
            re.search(
                rf"\b(pytest|py\.test|{PYTHON_CMD}\s+-m\s+pytest|jest|mocha|"
                r"cargo\s+test|go\s+test|rspec|phpunit|vitest|bun\s+test|"
                r"npm\s+test|yarn\s+test|pnpm\s+test|"
                r"dotnet\s+test|swift\s+test|mix\s+test|"
                r"npx\s+(jest|mocha|vitest|playwright)|"
                r"poetry\s+run\s+(pytest|py\.test)|uv\s+run\s+(pytest|py\.test)|"
                r"pipx\s+run\s+pytest|bundle\s+exec\s+(rspec|rails\s+test))\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()

        if re.search(
            rf"\bpytest\b|py\.test|{PYTHON_CMD}\s+-m\s+pytest"
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
        result = []
        in_failure = False
        in_warnings = False
        failure_block: list[str] = []
        warning_lines: list[str] = []
        summary_lines = []
        passed_count = 0
        param_tests: dict[str, dict] = {}  # base_name -> {"passed": int, "failed": [param]}

        for line in lines:
            # Skip collection output
            if re.match(r"^(collecting|collected)\s", line.strip()):
                continue
            # Skip platform/rootdir/configfile lines
            if re.match(r"^(platform|rootdir|configfile|plugins|cachedir)[\s:]", line.strip()):
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
                    r"^=+ (short test summary|warnings summary|\d+ (failed|passed|error))", line
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
                    base = m.group(1)
                    param_tests.setdefault(base, {"passed": 0, "failed": []})
                    param_tests[base]["passed"] += 1
                continue

            # Keep FAILED/ERROR individual lines
            if re.search(r"\bFAILED\b|\bERROR\b", line):
                # Track parameterized test failures
                m = re.match(r"^(\S+?)\[(.+)\]\s+FAILED", line.strip())
                if m:
                    base = m.group(1)
                    param = m.group(2)
                    param_tests.setdefault(base, {"passed": 0, "failed": []})
                    param_tests[base]["failed"].append(param)
                else:
                    result.append(line)
                continue

            # Keep final summary lines (skip "test session starts" header)
            if re.match(r"^=+.*=+$", line) and "test session starts" not in line:
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
        for base, info in param_tests.items():
            if info["failed"]:
                total = info["passed"] + len(info["failed"])
                failed_params = ", ".join(info["failed"][:5])
                extra = ""
                if len(info["failed"]) > 5:
                    extra = f", ... ({len(info['failed']) - 5} more)"
                result.append(
                    f"{base}: {info['passed']}/{total} passed, FAILED: [{failed_params}{extra}]"
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
                re.match(r"^-+ coverage", stripped) or re.match(r"^Name\s+Stmts\s+Miss", stripped)
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
            result.append(f"Files below 80% coverage ({len(low_coverage_files)}):")
            for f in low_coverage_files[:10]:
                result.append(f"  {f}")
            if len(low_coverage_files) > 10:
                result.append(f"  ... ({len(low_coverage_files) - 10} more)")

        return result

    def _collapse_warnings(self, warning_lines: list[str]) -> list[str]:
        """Group warnings by type, show count + one example per type."""
        by_type: dict[str, list[str]] = {}
        for line in warning_lines:
            # Extract warning type: "DeprecationWarning: ...", "UserWarning: ...", etc.
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
        for wtype, instances in sorted(by_type.items(), key=lambda x: -len(x[1])):
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
        result = []
        in_failure = False
        passed_suites = 0
        passed_tests = 0
        failure_buffer: list[str] = []
        consecutive_blanks = 0

        for line in lines:
            stripped = line.strip()

            # Capture failure blocks
            if re.search(r"\bFAIL\b", line) and not re.match(r"^(Tests?|Test Suites?):", stripped):
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

            if re.search(r"\bPASS\b", line) and not re.match(r"^(Tests?|Test Suites?):", stripped):
                passed_suites += 1
                m = re.search(r"\((\d+)\s+tests?\)", line)
                if m:
                    passed_tests += int(m.group(1))
                continue

            # Keep summary lines
            if re.match(r"^(Tests?|Test Suites?|Snapshots?|Time|Ran all):", stripped):
                result.append(line)

        if failure_buffer:
            result.extend(self._truncate_traceback(failure_buffer))

        if passed_suites > 0:
            result.insert(0, f"[{passed_suites} suites passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_cargo_test(self, lines: list[str]) -> str:
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
            if re.match(r"^\s*(Compiling|Downloading|Running|Doc-tests)", stripped):
                continue

        if ok_count > 0:
            result.insert(0, f"[{ok_count} tests passed]")

        return "\n".join(result) if result else "\n".join(lines)

    def _process_go_test(self, lines: list[str]) -> str:
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
                stripped.startswith("Passed!") or re.search(r"\bPassed\b", stripped)
            ) and "test" not in stripped.lower():
                passed += 1
                continue

            if re.search(r"\bFailed\b", stripped):
                in_failure = True
                result.append(line)
                continue

            if in_failure:
                result.append(line)
                if not stripped or re.match(r"^(Total|Passed|Failed|Skipped)\s", stripped):
                    in_failure = False
                continue

            # Summary lines
            if re.match(r"^(Total tests|Passed|Failed|Skipped|Test Run)", stripped):
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
            if re.match(r"^Test Suite", stripped) or re.match(r"^Executed \d+", stripped):
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
        result = []
        passed = 0

        for line in lines:
            lower = line.lower()
            if any(kw in lower for kw in ["fail", "error", "assert", "exception", "traceback"]):
                result.append(line)
            elif any(kw in lower for kw in ["pass", "ok ", "success"]) or re.match(
                r"^\s*(✓|✔)", line.strip()
            ):
                passed += 1
            elif re.match(r"^\d+\s+(tests?|specs?|examples?)", line.strip()):
                result.append(line)

        if passed > 0:
            result.insert(0, f"[{passed} tests passed]")

        return "\n".join(result) if result else "\n".join(lines[-10:])
