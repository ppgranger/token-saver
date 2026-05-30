"""mise processor: mise install, use, upgrade (runtime version manager)."""

import re

from .base import Processor

_MISE_CMD_RE = re.compile(r"\bmise\s+(install|use|upgrade|up|i)\b")
_PROGRESS_RE = re.compile(
    r"^\s*(mise\s+)?(downloading|extracting|verifying|fetching|building|compiling)\b",
    re.IGNORECASE,
)
_INSTALLED_RE = re.compile(r"\b(installed|installing)\b\s+\S+@\S", re.IGNORECASE)
_ERROR_RE = re.compile(r"\b(error|Error|failed|Failed|warn|WARN|warning)\b")


class MiseProcessor(Processor):
    priority = 49
    hook_patterns = [
        r"^mise\s+(install|use|upgrade|up|i)\b",
    ]

    @property
    def name(self) -> str:
        return "mise"

    def can_handle(self, command: str) -> bool:
        return bool(_MISE_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
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
