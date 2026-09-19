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

"""Bun package processor: bun install, add, remove, update."""

import re

from src.processors import base

_BUN_CMD_RE = re.compile(r"\bbun\s+(install|add|remove|rm|update|i)\b")
_INSTALLED_RE = re.compile(r"^\s*(installed|\+|-)\s+\S")
_SUMMARY_RE = re.compile(r"\b\d+\s+packages?\s+(installed|removed)\b")
_NOISE_RE = re.compile(
    r"^\s*(Resolving|Resolved|Saved lockfile|Downloading|Extracting|Linking)\b"
)
_ERROR_RE = re.compile(
    r"\b(error|Error|failed|Failed|warn|warning|EACCES|ENOENT)\b"
)


class BunProcessor(base.Processor):
    """Summarize Bun installations, tests, and builds with diagnostics."""

    priority = 29
    handles_failure = True
    hook_patterns = [
        r"^bun\s+(install|add|remove|rm|update|i)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "bun"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(_BUN_CMD_RE.search(command))

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
        if len(lines) <= 10:
            return output

        pkg_lines: list[str] = []
        summary_lines: list[str] = []
        errors: list[str] = []
        noise = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _SUMMARY_RE.search(stripped):
                summary_lines.append(stripped)
            elif _ERROR_RE.search(stripped):
                errors.append(line)
            elif _INSTALLED_RE.match(stripped):
                pkg_lines.append(f"  {stripped}")
            elif _NOISE_RE.match(stripped):
                noise += 1

        result: list[str] = []
        if errors:
            result.extend(errors)
        if pkg_lines:
            result.append(f"{len(pkg_lines)} package changes:")
            result.extend(pkg_lines[:10])
            if len(pkg_lines) > 10:
                result.append(f"  ... ({len(pkg_lines) - 10} more)")
        if noise:
            result.append(f"[{noise} resolve/download steps]")
        result.extend(summary_lines)

        return "\n".join(result) if result else output
