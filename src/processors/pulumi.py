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

"""Pulumi processor: pulumi up, preview, destroy, refresh."""

import re

from src.processors import base

_PULUMI_CMD_RE = re.compile(r"\bpulumi\s+(up|update|preview|destroy|refresh)\b")
# Resource operation lines start with a +/-/~ marker (create/delete/update).
_RESOURCE_OP_RE = re.compile(r"^\s*[+\-~]\s+\S")
_KEEP_RE = re.compile(
    (
        r"^(Updating|Previewing|Destroying|Refreshing|Resources:|Outputs:|"
        r"Duration:|Diagnostics:)"
    ),
)
_ERROR_RE = re.compile(r"\b(error|Error|warning|Warning|failed|Failed|panic)\b")
# Bullet lines carrying the detail of a multi-error report.
_ERROR_BULLET_RE = re.compile(r"^[*\-]\s+\S")


class PulumiProcessor(base.Processor):
    """Summarize Pulumi resource updates and recognized diagnostics."""

    priority = 46
    handles_failure = True
    hook_patterns = [
        r"^pulumi\s+(up|update|preview|destroy|refresh)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "pulumi"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(_PULUMI_CMD_RE.search(command))

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
        if len(lines) <= 20:
            return output

        result: list[str] = []
        in_summary = False
        in_error = False
        skipped = 0

        for line in lines:
            stripped = line.strip()

            if _KEEP_RE.match(stripped):
                # Resources:/Outputs:/Diagnostics: open a block we keep
                # verbatim.
                in_summary = stripped.startswith(
                    ("Resources:", "Outputs:", "Diagnostics:")
                )
                in_error = False
                result.append(line)
                continue

            # Inside a summary block, keep indented detail lines.
            if in_summary and (line.startswith((" ", "\t")) and stripped):
                result.append(line)
                continue
            if in_summary and not stripped:
                in_summary = False

            if _RESOURCE_OP_RE.match(line) or _ERROR_RE.search(stripped):
                # `error: 1 error occurred:` is followed by indented bullet
                # lines carrying the actual reason ("* creating bucket:
                # BucketAlreadyExists").  Those bullets match neither the
                # resource-op marker nor the error vocabulary, so without this
                # the header survives and the reason is counted as progress
                # noise — the one thing that must never happen.
                in_error = bool(_ERROR_RE.search(stripped))
                result.append(line)
                continue

            # Continuation of an error block: indented detail, or a bullet.
            if (
                in_error
                and stripped
                and (
                    line.startswith((" ", "\t"))
                    or _ERROR_BULLET_RE.match(stripped)
                )
            ):
                result.append(line)
                continue
            in_error = False

            if stripped:
                skipped += 1

        if skipped:
            result.append(f"[{skipped} unchanged/progress lines hidden]")

        return "\n".join(result) if result else output
