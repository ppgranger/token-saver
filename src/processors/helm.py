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

"""Helm output processor: install, upgrade, list, template, status."""

import re

from src.processors import base


class HelmProcessor(base.Processor):
    """Summarize Helm manifests, releases, and deployment status."""

    priority = 41
    handles_failure = True
    hook_patterns = [
        (
            r"^helm\s+(install|upgrade|list|template|status|rollback|history|"
            r"uninstall|get)\b"
        ),
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "helm"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(
            re.search(
                r"\bhelm\s+(install|upgrade|list|template|status|rollback|"
                r"history|uninstall|get)\b",
                command,
            )
        )

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

        if re.search(r"\bhelm\s+template\b", command):
            return self._process_template(output)
        if re.search(r"\bhelm\s+(install|upgrade)\b", command):
            return self._process_install(output)
        if re.search(r"\bhelm\s+list\b", command):
            return self._process_list(output)
        if re.search(r"\bhelm\s+status\b", command):
            return self._process_install(output)
        if re.search(r"\bhelm\s+history\b", command):
            return self._process_history(output)
        return output

    def _process_template(self, output: str) -> str:
        """Compress helm template: summarize YAML manifests."""
        lines = output.splitlines()
        if len(lines) <= 50:
            return output

        manifests: list[tuple[str, int]] = []
        current_kind = ""
        current_name = ""
        current_lines = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if current_kind:
                    manifests.append(
                        (f"{current_kind}/{current_name}", current_lines)
                    )
                current_kind = ""
                current_name = ""
                current_lines = 0
                continue
            if stripped.startswith("kind:"):
                current_kind = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("  name:") or (
                stripped.startswith("name:") and not current_name
            ):
                current_name = stripped.split(":", 1)[1].strip()
            current_lines += 1

        if current_kind:
            manifests.append((f"{current_kind}/{current_name}", current_lines))

        result = [
            (
                f"helm template: {len(manifests)} manifests, {len(lines)} "
                f"lines total:"
            )
        ]
        for manifest, count in manifests:
            result.append(f"  {manifest} ({count} lines)")
        return "\n".join(result)

    def _process_install(self, output: str) -> str:
        """Keep Helm deployment status while removing NOTES boilerplate."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        in_notes = False
        notes_count = 0

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("NOTES:"):
                in_notes = True
                notes_count = 0
                continue

            if in_notes:
                notes_count += 1
                continue

            if stripped:
                result.append(line)

        if notes_count > 0:
            result.append(f"[NOTES section omitted ({notes_count} lines)]")

        return "\n".join(result) if result else output

    def _process_list(self, output: str) -> str:
        """Compress helm list: truncate long lists."""
        lines = output.splitlines()
        if len(lines) <= 25:
            return output

        result = [lines[0]]
        result.extend(lines[1:20])
        result.append(f"... ({len(lines) - 21} more releases)")
        return "\n".join(result)

    def _process_history(self, output: str) -> str:
        """Compress helm history: truncate old revisions."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output
        result = [lines[0]]
        result.insert(1, f"... ({len(lines) - 11} older revisions)")
        result.extend(lines[-10:])
        return "\n".join(result)
