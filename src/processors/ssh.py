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

"""SSH processor: non-interactive SSH and SCP commands."""

import re

from src.processors import base
from src.processors import utils

_SSH_NON_INTERACTIVE_RE = re.compile(r"""\bssh\s+.+\s+['"]""")
_SCP_RE = re.compile(r"\bscp\b")
_SCP_PROGRESS_RE = re.compile(r"^\s*\S+\s+\d+%")


class SshProcessor(base.Processor):
    """Summarize remote logs and file transfer progress from SSH tools."""

    priority = 43
    hook_patterns = [
        r"^ssh\s+.+\s+['\"]",
        r"^scp\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "ssh"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        if _SCP_RE.search(command):
            return True
        if re.search(r"\bssh\b", command):
            return bool(_SSH_NON_INTERACTIVE_RE.search(command))
        return False

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

        if _SCP_RE.search(command):
            return self._process_scp(output)
        return self._process_ssh_remote(output)

    def _process_ssh_remote(self, output: str) -> str:
        """Summarize remote command output using error-aware log compression."""
        lines = output.splitlines()
        return utils.compress_log_lines(lines, keep_head=10, keep_tail=20)

    def _process_scp(self, output: str) -> str:
        """Remove transfer progress and retain completed files and errors."""
        lines = output.splitlines()
        result: list[str] = []
        last_progress: str | None = None

        for line in lines:
            stripped = line.strip()

            if _SCP_PROGRESS_RE.match(stripped):
                last_progress = line
            elif re.search(
                r"\b(error|Error|ERROR|denied|refused|No such)\b", stripped
            ):
                result.append(line)
            elif stripped and not _SCP_PROGRESS_RE.match(stripped):
                if last_progress:
                    result.append(last_progress)
                    last_progress = None
                result.append(line)

        # Flush final progress line
        if last_progress:
            result.append(last_progress)

        return "\n".join(result) if result else output
