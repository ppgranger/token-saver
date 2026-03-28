"""Maven/Gradle processor: mvn, gradle, gradlew, mvnw builds."""

import re

from .base import Processor

_MVN_RE = re.compile(r"\b(mvn|\.?/?mvnw)\b")
_GRADLE_RE = re.compile(r"\b(gradle|\.?/?gradlew)\b")

# Maven patterns
_MVN_DOWNLOAD_RE = re.compile(r"^\[INFO\]\s+(Downloading|Downloaded)\s+from\s+")
_MVN_MODULE_RE = re.compile(r"^\[INFO\]\s+Building\s+(.+?)\s+\[")
_MVN_SEPARATOR_RE = re.compile(r"^\[INFO\]\s+-{10,}")
_MVN_ERROR_RE = re.compile(r"^\[(ERROR|FATAL)\]")
_MVN_WARNING_RE = re.compile(r"^\[WARNING\]")
_MVN_BUILD_RESULT_RE = re.compile(r"^\[INFO\]\s+(BUILD\s+(SUCCESS|FAILURE))")
_MVN_TEST_RESULT_RE = re.compile(r"^\[INFO\]\s+Tests run:\s+(\d+)")
_MVN_REACTOR_RE = re.compile(r"^\[INFO\]\s+Reactor Summary")
_MVN_TOTAL_TIME_RE = re.compile(r"^\[INFO\]\s+Total time:")
_MVN_EMPTY_INFO_RE = re.compile(r"^\[INFO\]\s*$")

# Gradle patterns
_GRADLE_TASK_RE = re.compile(r"^>\s+Task\s+:(\S+)")
_GRADLE_UPTODATE_RE = re.compile(r"\b(UP-TO-DATE|NO-SOURCE|SKIPPED|FROM-CACHE)\s*$")
_GRADLE_BUILD_RESULT_RE = re.compile(r"^(BUILD\s+(SUCCESSFUL|FAILED))")
_GRADLE_ACTIONABLE_RE = re.compile(r"^\d+\s+actionable\s+task")
_GRADLE_ERROR_RE = re.compile(
    r"^(FAILURE:|>\s+.*[Ee]rror|e:\s+|"
    r"\s+What went wrong|\s+Execution failed)"
)
_GRADLE_TEST_RESULT_RE = re.compile(r"^\d+\s+tests?\s+(completed|passed|failed)")


class MavenGradleProcessor(Processor):
    priority = 28
    hook_patterns = [
        r"^(\.?/?mvnw?|\.?/?gradlew?)\b",
    ]

    @property
    def name(self) -> str:
        return "maven_gradle"

    def can_handle(self, command: str) -> bool:
        return bool(_MVN_RE.search(command) or _GRADLE_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if _GRADLE_RE.search(command):
            return self._process_gradle(output)
        return self._process_maven(output)

    def _process_maven(self, output: str) -> str:
        lines = output.splitlines()
        result: list[str] = []
        download_count = 0
        module_count = 0
        errors: list[str] = []
        warnings: list[str] = []
        test_results: list[str] = []
        in_reactor = False
        reactor_lines: list[str] = []
        build_result = ""
        timing_line = ""
        separator_count = 0

        for line in lines:
            stripped = line.strip()

            if _MVN_DOWNLOAD_RE.match(stripped):
                download_count += 1
                continue

            if _MVN_MODULE_RE.match(stripped):
                module_count += 1
                continue

            if _MVN_SEPARATOR_RE.match(stripped):
                separator_count += 1
                continue

            if _MVN_EMPTY_INFO_RE.match(stripped):
                continue

            if _MVN_REACTOR_RE.match(stripped):
                in_reactor = True
                reactor_lines.append(line)
                continue

            if in_reactor:
                if _MVN_BUILD_RESULT_RE.match(stripped) or _MVN_TOTAL_TIME_RE.match(stripped):
                    in_reactor = False
                else:
                    reactor_lines.append(line)
                    continue

            if _MVN_BUILD_RESULT_RE.match(stripped):
                build_result = line
                continue

            if _MVN_TOTAL_TIME_RE.match(stripped):
                timing_line = line
                continue

            if _MVN_TEST_RESULT_RE.match(stripped):
                test_results.append(line)
                continue

            if _MVN_ERROR_RE.match(stripped):
                errors.append(line)
                continue

            if _MVN_WARNING_RE.match(stripped):
                warnings.append(line)
                continue

        # Build compressed output
        summary_parts = []
        if module_count:
            summary_parts.append(f"{module_count} modules")
        if download_count:
            summary_parts.append(f"{download_count} downloads")
        if summary_parts:
            result.append(f"[{', '.join(summary_parts)}]")

        if errors:
            result.extend(errors)

        if warnings:
            if len(warnings) > 5:
                result.extend(warnings[:5])
                result.append(f"... ({len(warnings) - 5} more warnings)")
            else:
                result.extend(warnings)

        if test_results:
            result.extend(test_results)

        if reactor_lines:
            result.extend(reactor_lines)

        if build_result:
            result.append(build_result)
        if timing_line:
            result.append(timing_line)

        return "\n".join(result) if result else output

    def _process_gradle(self, output: str) -> str:
        lines = output.splitlines()
        result: list[str] = []
        skipped_tasks = 0
        executed_tasks: list[str] = []
        errors: list[str] = []
        test_results: list[str] = []
        build_result = ""
        actionable_line = ""
        in_error_block = False

        for line in lines:
            stripped = line.strip()

            m = _GRADLE_TASK_RE.match(stripped)
            if m:
                if _GRADLE_UPTODATE_RE.search(stripped):
                    skipped_tasks += 1
                else:
                    executed_tasks.append(m.group(1))
                in_error_block = False
                continue

            if _GRADLE_BUILD_RESULT_RE.match(stripped):
                build_result = line
                in_error_block = False
                continue

            if _GRADLE_ACTIONABLE_RE.match(stripped):
                actionable_line = line
                continue

            if _GRADLE_TEST_RESULT_RE.match(stripped):
                test_results.append(line)
                continue

            if _GRADLE_ERROR_RE.match(stripped):
                in_error_block = True
                errors.append(line)
                continue

            if in_error_block and stripped:
                errors.append(line)
                continue

        # Build compressed output
        summary_parts = []
        if executed_tasks:
            summary_parts.append(f"{len(executed_tasks)} executed")
        if skipped_tasks:
            summary_parts.append(f"{skipped_tasks} up-to-date")
        if summary_parts:
            result.append(f"Tasks: {', '.join(summary_parts)}")

        if executed_tasks and len(executed_tasks) <= 10:
            for task in executed_tasks:
                result.append(f"  :{task}")
        elif executed_tasks:
            for task in executed_tasks[:5]:
                result.append(f"  :{task}")
            result.append(f"  ... ({len(executed_tasks) - 5} more)")

        if errors:
            result.extend(errors)

        if test_results:
            result.extend(test_results)

        if build_result:
            result.append(build_result)
        if actionable_line:
            result.append(actionable_line)

        return "\n".join(result) if result else output
