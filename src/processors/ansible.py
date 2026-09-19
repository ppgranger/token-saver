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

"""Ansible output processor: ansible-playbook, ansible."""

import re

from src.processors import base


class AnsibleProcessor(base.Processor):
    """Summarize Ansible tasks while retaining changes and failure recaps."""

    priority = 40
    handles_failure = True
    hook_patterns = [
        r"^ansible(-playbook)?\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "ansible"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(re.search(r"\b(ansible-playbook|ansible)\b", command))

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

        result = []
        ok_count = 0
        skipped_count = 0
        in_recap = False

        for line in lines:
            stripped = line.strip()

            # PLAY RECAP is always kept in full
            if stripped.startswith("PLAY RECAP"):
                in_recap = True
                result.append(line)
                continue

            if in_recap:
                result.append(line)
                continue

            # PLAY and TASK headers — keep
            if re.match(r"^(PLAY|TASK)\s+\[", stripped):
                result.append(line)
                continue

            # Separator lines (****)
            if re.match(r"^\*+$", stripped):
                continue

            # changed — always keep
            if re.match(r"^changed:", stripped):
                result.append(line)
                continue

            # failed / fatal / unreachable — always keep
            if re.match(r"^(fatal|failed|unreachable):", stripped, re.I):
                result.append(line)
                continue

            # Error/warning output lines (indented after fatal/failed)
            if re.search(r"\b(ERROR|FAILED|UNREACHABLE|fatal)\b", stripped):
                result.append(line)
                continue

            # "msg:" lines (error messages) — keep
            if re.match(r'^\s*"?msg"?\s*:', stripped):
                result.append(line)
                continue

            # ok — count and skip
            if re.match(r"^ok:", stripped):
                ok_count += 1
                continue

            # skipping — count and skip
            if re.match(r"^skipping:", stripped):
                skipped_count += 1
                continue

            # included/imported — skip
            if re.match(r"^(included|imported):", stripped):
                continue

        # Insert summary at the top
        summary_parts = []
        if ok_count:
            summary_parts.append(f"{ok_count} ok")
        if skipped_count:
            summary_parts.append(f"{skipped_count} skipped")
        if summary_parts:
            result.insert(0, f"[{', '.join(summary_parts)}]")

        return "\n".join(result) if result else output
