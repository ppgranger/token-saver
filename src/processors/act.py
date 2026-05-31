"""act processor: run GitHub Actions locally (nektos/act)."""

import re

from .base import Processor

_ACT_CMD_RE = re.compile(r"(^|\s)act(\s|$)")
# Docker/setup chrome that adds no debugging value.
_CHROME_RE = re.compile(
    r"🚀\s+Start|🐳\s+docker|☁\s+git|Cleaning up|"
    r"docker (pull|create|exec|cp|rm|run)\b|"
    r"Removed container|Created container|Prepare|Pulling",
)
# Lines we always keep: step run markers, results, job status, errors, and the
# command output the workflow itself emitted (prefixed with "| ").
_KEEP_RE = re.compile(r"⭐|✅|❌|🏁|Success|Failure|Job\s+(succeeded|failed)|^\s*\|")
_ERROR_RE = re.compile(r"\b(error|Error|ERROR|failed|Failed|FAILED|panic)\b")


class ActProcessor(Processor):
    priority = 19
    hook_patterns = [
        r"^act(\s|$)",
    ]

    @property
    def name(self) -> str:
        return "act"

    def can_handle(self, command: str) -> bool:
        return bool(re.match(r"^\s*act(\s|$)", command))

    def process(self, command: str, output: str) -> str:
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
