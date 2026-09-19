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

"""Cargo processor: cargo build, check, doc, update, bench."""

import collections
import re

from src import config
from src.processors import base
from src.processors import utils

_CARGO_CMD_RE = re.compile(r"\bcargo\s+(build|check|doc|update|bench)\b")
_DOWNLOADING_RE = re.compile(r"^\s*Downloading\s+\S+\s+v")
_DOCUMENTING_RE = re.compile(r"^\s*Documenting\s+\S+\s+v")
_RUNNING_RE = re.compile(r"^\s*Running\s+")
_UPDATE_LINE_RE = re.compile(
    r"^\s*(Updating|Removing|Adding)\s+(\S+)\s+v([\d.]+)(?:\s*->\s*v([\d.]+))?"
)


class CargoProcessor(base.Processor):
    """Summarize Cargo compilation, documentation, updates, and benchmarks."""

    priority = 22
    handles_failure = True
    hook_patterns = [
        r"^cargo\s+(build|check|doc|update|bench)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "cargo"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        if re.search(r"\bcargo\s+(test|clippy)\b", command):
            return False
        return bool(_CARGO_CMD_RE.search(command))

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

        m = _CARGO_CMD_RE.search(command)
        if not m:
            return output

        subcmd = m.group(1)
        if subcmd in ("build", "check"):
            return self._process_cargo_build(output)
        if subcmd == "doc":
            return self._process_cargo_doc(output)
        if subcmd == "update":
            return self._process_cargo_update(output)
        if subcmd == "bench":
            return self._process_cargo_bench(output)
        return output

    def _categorize_warning(self, msg: str) -> str:
        """Return a stable category for a Rust compiler warning message."""
        if "unused variable" in msg:
            return "unused_variable"
        if "unused import" in msg:
            return "unused_import"
        if "dead_code" in msg or "never read" in msg or "never used" in msg:
            return "dead_code"
        if "does not need to be mutable" in msg:
            return "unused_mut"
        if "lifetime" in msg:
            return "lifetime"
        if "borrow" in msg:
            return "borrow_checker"
        m = re.search(r"\[(\w+(?:::\w+)*)\]", msg)
        return m.group(1) if m else "other"

    def _process_cargo_build(self, output: str) -> str:
        """Group compiler warnings and preserve complete compiler errors."""
        lines = output.splitlines()
        result: list[str] = []
        compiling_count = 0
        downloading_count = 0

        warnings_by_type: dict[str, list[list[str]]] = collections.defaultdict(
            list
        )
        current_block: list[str] = []
        current_type: str | None = None
        in_error = False
        error_blocks: list[list[str]] = []
        current_error: list[str] = []
        finished_lines: list[str] = []
        warning_summary_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            if utils.RUST_COMPILING_RE.match(stripped):
                compiling_count += 1
                continue
            if _DOWNLOADING_RE.match(stripped):
                downloading_count += 1
                continue

            # Error start
            if utils.RUST_ERROR_START_RE.match(stripped):
                # Flush current warning block
                if current_type and current_block:
                    warnings_by_type[current_type].append(current_block)
                    current_block = []
                    current_type = None
                # Start error block
                if in_error and current_error:
                    error_blocks.append(current_error)
                in_error = True
                current_error = [line]
                continue

            # Warning start
            wm = utils.RUST_WARNING_START_RE.match(stripped)
            if wm and not utils.RUST_WARNING_SUMMARY_RE.match(stripped):
                # Flush previous
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                if current_type and current_block:
                    warnings_by_type[current_type].append(current_block)

                rule = wm.group(1) or ""
                msg = wm.group(2)
                current_type = self._categorize_warning(rule + " " + msg)
                current_block = [line]
                continue

            if utils.RUST_WARNING_SUMMARY_RE.match(stripped):
                if current_type and current_block:
                    warnings_by_type[current_type].append(current_block)
                    current_block = []
                    current_type = None
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                warning_summary_lines.append(line)
                continue

            if utils.RUST_FINISHED_RE.match(stripped):
                if current_type and current_block:
                    warnings_by_type[current_type].append(current_block)
                    current_block = []
                    current_type = None
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                finished_lines.append(line)
                continue

            # Context lines (spans, code, etc.)
            if in_error:
                current_error.append(line)
            elif current_type:
                current_block.append(line)

        # Flush remaining
        if in_error and current_error:
            error_blocks.append(current_error)
        if current_type and current_block:
            warnings_by_type[current_type].append(current_block)

        # Build compressed output
        if downloading_count > 0:
            result.append(f"[{downloading_count} crates downloaded]")
        if compiling_count > 0:
            result.append(f"[{compiling_count} crates compiled]")

        # All errors (kept in full)
        for block in error_blocks:
            result.extend(block)

        # Grouped warnings
        example_count = config.get("cargo_warning_example_count")
        group_threshold = config.get("cargo_warning_group_threshold")
        for wtype, blocks in sorted(
            warnings_by_type.items(), key=lambda x: -len(x[1])
        ):
            count = len(blocks)
            if count >= group_threshold:
                result.append(f"warning: {wtype} ({count} occurrences)")
                for block in blocks[:example_count]:
                    result.extend(f"  {line}" for line in block)
                if count > example_count:
                    result.append(f"  ... ({count - example_count} more)")
            else:
                for block in blocks:
                    result.extend(block)

        result.extend(warning_summary_lines)
        result.extend(finished_lines)

        return "\n".join(result) if result else output

    def _process_cargo_doc(self, output: str) -> str:
        """Count documented crates while retaining warnings and result lines."""
        lines = output.splitlines()
        result: list[str] = []
        compiling_count = 0
        documenting_count = 0

        for line in lines:
            stripped = line.strip()
            if utils.RUST_COMPILING_RE.match(stripped):
                compiling_count += 1
            elif _DOCUMENTING_RE.match(stripped):
                documenting_count += 1
            elif (
                utils.RUST_FINISHED_RE.match(stripped)
                or re.match(r"^\s*Generated\s+", stripped)
                or re.search(r"\bwarning\b", stripped)
                or utils.RUST_ERROR_START_RE.match(stripped)
                or (utils.RUST_SPAN_LINE_RE.match(stripped) and result)
            ):
                result.append(line)

        summary_parts = []
        if compiling_count > 0:
            summary_parts.append(f"{compiling_count} compiled")
        if documenting_count > 0:
            summary_parts.append(f"{documenting_count} documented")
        if summary_parts:
            result.insert(0, f"[{', '.join(summary_parts)}]")

        return "\n".join(result) if result else output

    def _process_cargo_update(self, output: str) -> str:
        """Group dependency version changes and retain update diagnostics."""
        lines = output.splitlines()
        updates: list[str] = []
        major_bumps: list[str] = []
        additions: list[str] = []
        removals: list[str] = []

        for line in lines:
            m = _UPDATE_LINE_RE.match(line.strip())
            if m:
                action, pkg, old_ver, new_ver = m.groups()
                if action == "Adding":
                    additions.append(f"  + {pkg} v{old_ver}")
                elif action == "Removing":
                    removals.append(f"  - {pkg} v{old_ver}")
                elif action == "Updating" and new_ver:
                    old_major = old_ver.split(".")[0]
                    new_major = new_ver.split(".")[0]
                    if old_major != new_major:
                        major_bumps.append(
                            f"  {pkg}: v{old_ver} -> v{new_ver} (MAJOR)"
                        )
                    else:
                        updates.append(pkg)

        result = []
        total = len(updates) + len(major_bumps)
        result.append(f"[{total} dependencies updated]")

        if major_bumps:
            result.append("Major version bumps:")
            result.extend(major_bumps)

        if updates:
            result.append(f"Minor/patch updates: {len(updates)} packages")

        if additions:
            result.append("Added:")
            result.extend(additions)
        if removals:
            result.append("Removed:")
            result.extend(removals)

        return "\n".join(result) if result else output

    def _process_cargo_bench(self, output: str) -> str:
        """Retain benchmark measurements and summarize compilation noise."""
        lines = output.splitlines()
        result: list[str] = []
        compiling_count = 0

        for line in lines:
            stripped = line.strip()
            if utils.RUST_COMPILING_RE.match(stripped):
                compiling_count += 1
            elif _RUNNING_RE.match(stripped):
                continue
            elif (
                re.match(r"^test\s+.+\s+bench:", stripped)
                or re.match(r"^test result:", stripped)
                or utils.RUST_FINISHED_RE.match(stripped)
                or utils.RUST_ERROR_START_RE.match(stripped)
            ):
                result.append(line)

        if compiling_count > 0:
            result.insert(0, f"[{compiling_count} crates compiled]")

        return "\n".join(result) if result else output
