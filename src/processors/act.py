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

"""act processor: run GitHub Actions locally (nektos/act)."""

import re

from src.processors import base

_ACT_CMD_RE = re.compile(r"(^|\s)act(\s|$)")
# Docker/setup chrome that adds no debugging value.
_CHROME_RE = re.compile(
    r"🚀\s+Start|🐳\s+docker|☁\s+git|Cleaning up|"
    r"docker (pull|create|exec|cp|rm|run)\b|"
    r"Removed container|Created container|Prepare|Pulling",
)
# Lines we always keep: step run markers, results, job status, errors, and the
# command output the workflow itself emitted (prefixed with "| ").
_KEEP_RE = re.compile(
    r"⭐|✅|❌|🏁|Success|Failure|Job\s+(succeeded|failed)|^\s*\|"
)
_ERROR_RE = re.compile(r"\b(error|Error|ERROR|failed|Failed|FAILED|panic)\b")


class ActProcessor(base.Processor):
    """Summarize local GitHub Actions runs and preserve failure details."""

    priority = 19
    handles_failure = True
    hook_patterns = [
        r"^act(\s|$)",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "act"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(re.match(r"^\s*act(\s|$)", command))

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
        if len(lines) <= 15:
            return output

        result: list[str] = []
        chrome = 0

        for line in lines:
            stripped = line.strip()
            if _KEEP_RE.search(line) or _ERROR_RE.search(stripped):
                result.append(line)
            elif _CHROME_RE.search(stripped):
                chrome += 1
            elif stripped:
                result.append(line)

        if chrome:
            result.append(f"[{chrome} docker/setup lines hidden]")

        return "\n".join(result) if result else output
