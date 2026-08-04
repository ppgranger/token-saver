"""System log processor: journalctl, dmesg."""

import re

from .. import config
from .base import Processor
from .utils import compress_log_lines


class SyslogProcessor(Processor):
    priority = 42
    handles_failure = True
    hook_patterns = [
        r"^(journalctl|dmesg)\b",
    ]

    @property
    def name(self) -> str:
        return "syslog"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(journalctl|dmesg)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        return compress_log_lines(
            lines,
            keep_head=10,
            keep_tail=20,
            context_lines=config.get("file_log_context_lines"),
        )
