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

"""mise processor: mise install, use, upgrade (runtime version manager)."""

import re

from src.processors import base

_MISE_CMD_RE = re.compile(r"\bmise\s+(install|use|upgrade|up|i)\b")
_PROGRESS_RE = re.compile(
    (
        r"^\s*(mise\s+)?(downloading|extracting|verifying|fetching|building|"
        r"compiling)\b"
    ),
    re.IGNORECASE,
)
_INSTALLED_RE = re.compile(
    r"\b(installed|installing)\b\s+\S+@\S", re.IGNORECASE
)
_ERROR_RE = re.compile(r"\b(error|Error|failed|Failed|warn|WARN|warning)\b")


class MiseProcessor(base.Processor):
    """Summarize Mise tool installation and execution progress."""

    priority = 49
    handles_failure = True
    hook_patterns = [
        r"^mise\s+(install|use|upgrade|up|i)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "mise"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(_MISE_CMD_RE.search(command))

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

        result: list[str] = []
        progress = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _ERROR_RE.search(stripped) or _INSTALLED_RE.search(stripped):
                result.append(line)
            elif _PROGRESS_RE.match(stripped):
                progress += 1
            else:
                result.append(line)

        if progress:
            result.append(f"[{progress} download/build steps]")

        return "\n".join(result) if result else output
