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

"""System log processor: journalctl, dmesg."""

import re

from src import config
from src.processors import base
from src.processors import utils


class SyslogProcessor(base.Processor):
    """Summarize system logs with surrounding context for error lines."""

    priority = 42
    handles_failure = True
    hook_patterns = [
        r"^(journalctl|dmesg)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "syslog"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(re.search(r"\b(journalctl|dmesg)\b", command))

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
        if len(lines) <= 30:
            return output

        return utils.compress_log_lines(
            lines,
            keep_head=10,
            keep_tail=20,
            context_lines=config.get("file_log_context_lines"),
        )
