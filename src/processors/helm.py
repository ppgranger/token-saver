"""Helm output processor: install, upgrade, list, template, status."""

import re

from .base import Processor


class HelmProcessor(Processor):
    priority = 41
    hook_patterns = [
        r"^helm\s+(install|upgrade|list|template|status|rollback|history|uninstall|get)\b",
    ]

    @property
    def name(self) -> str:
        return "helm"

    def can_handle(self, command: str) -> bool:
        return bool(
            re.search(
                r"\bhelm\s+(install|upgrade|list|template|status|rollback|"
                r"history|uninstall|get)\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
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
                    manifests.append((f"{current_kind}/{current_name}", current_lines))
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

        result = [f"helm template: {len(manifests)} manifests, {len(lines)} lines total:"]
        for manifest, count in manifests:
            result.append(f"  {manifest} ({count} lines)")
        return "\n".join(result)

    def _process_install(self, output: str) -> str:
        """Compress helm install/upgrade/status: keep status, skip NOTES boilerplate."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        in_notes = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("NOTES:"):
                in_notes = True
                result.append("[NOTES section omitted]")
                continue

            if in_notes:
                if (
                    stripped
                    and not line.startswith((" ", "\t"))
                    and not stripped.startswith("NOTES:")
                ):
                    in_notes = False
                    result.append(line)
                continue

            if stripped:
                result.append(line)

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
