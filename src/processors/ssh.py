"""SSH processor: non-interactive SSH and SCP commands."""

import re

from .base import Processor
from .utils import compress_log_lines

_SSH_NON_INTERACTIVE_RE = re.compile(r"""\bssh\s+.+\s+['"]""")
_SCP_RE = re.compile(r"\bscp\b")
_SCP_PROGRESS_RE = re.compile(r"^\s*\S+\s+\d+%")


class SshProcessor(Processor):
    priority = 43
    hook_patterns = [
        r"^ssh\s+.+\s+['\"]",
        r"^scp\b",
    ]

    @property
    def name(self) -> str:
        return "ssh"

    def can_handle(self, command: str) -> bool:
        if _SCP_RE.search(command):
            return True
        if re.search(r"\bssh\b", command):
            return bool(_SSH_NON_INTERACTIVE_RE.search(command))
        return False

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if _SCP_RE.search(command):
            return self._process_scp(output)
        return self._process_ssh_remote(output)

    def _process_ssh_remote(self, output: str) -> str:
        lines = output.splitlines()
        return compress_log_lines(lines, keep_head=10, keep_tail=20)

    def _process_scp(self, output: str) -> str:
        lines = output.splitlines()
        result: list[str] = []
        last_progress: str | None = None

        for line in lines:
            stripped = line.strip()

            if _SCP_PROGRESS_RE.match(stripped):
                last_progress = line
            elif re.search(r"\b(error|Error|ERROR|denied|refused|No such)\b", stripped):
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
