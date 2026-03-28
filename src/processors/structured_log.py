"""Structured log processor: JSON Lines output from stern, kubetail, and similar tools."""

import json
import re
from collections import defaultdict

from .. import config
from .base import Processor
from .utils import compress_log_lines

_STERN_RE = re.compile(r"\b(stern|kubetail)\b")

# Common JSON log level keys
_LEVEL_KEYS = ("level", "severity", "log_level", "loglevel", "lvl", "log.level")
_MESSAGE_KEYS = ("msg", "message", "text", "log", "body")
_TIMESTAMP_KEYS = ("timestamp", "time", "ts", "@timestamp", "datetime", "date")

_ERROR_LEVELS = {"error", "fatal", "critical", "panic", "err", "crit", "emerg", "alert"}
_WARN_LEVELS = {"warn", "warning"}


class StructuredLogProcessor(Processor):
    priority = 45
    hook_patterns = [
        r"^(stern|kubetail)\b",
    ]

    @property
    def name(self) -> str:
        return "structured_log"

    def can_handle(self, command: str) -> bool:
        return bool(_STERN_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) < 5:
            return output

        # Try to parse as JSON lines
        parsed_lines: list[dict | None] = []
        json_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                parsed_lines.append(None)
                continue
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    parsed_lines.append(obj)
                    json_count += 1
                else:
                    parsed_lines.append(None)
            except (json.JSONDecodeError, ValueError):
                parsed_lines.append(None)

        non_empty = sum(1 for line in lines if line.strip())
        # If less than 50% lines are JSON objects, fall back to log compression
        if non_empty == 0 or json_count / non_empty < 0.5:
            keep_head = config.get("kubectl_keep_head")
            keep_tail = config.get("kubectl_keep_tail")
            return compress_log_lines(lines, keep_head=keep_head, keep_tail=keep_tail)

        return self._process_json_lines(lines, parsed_lines)

    def _process_json_lines(self, raw_lines: list[str], parsed: list[dict | None]) -> str:
        # Group by level
        level_counts: dict[str, int] = defaultdict(int)
        error_lines: list[str] = []
        total = 0

        for i, obj in enumerate(parsed):
            if obj is None:
                continue
            total += 1
            level = self._extract_level(obj)
            level_counts[level] += 1

            if level in _ERROR_LEVELS:
                msg = self._extract_message(obj)
                if msg:
                    error_lines.append(f"  [{level.upper()}] {msg}")
                else:
                    # Keep raw line but truncate
                    raw = raw_lines[i].strip()
                    if len(raw) > 200:
                        raw = raw[:197] + "..."
                    error_lines.append(f"  {raw}")

        result = [f"{total} log entries:"]

        # Level summary
        for level in (
            "error",
            "fatal",
            "critical",
            "panic",
            "warn",
            "warning",
            "info",
            "debug",
            "trace",
        ):
            if level in level_counts:
                result.append(f"  {level}: {level_counts[level]}")

        # Other levels not in the standard list
        for level, count in sorted(level_counts.items(), key=lambda x: -x[1]):
            if level not in (
                "error",
                "fatal",
                "critical",
                "panic",
                "warn",
                "warning",
                "info",
                "debug",
                "trace",
            ):
                result.append(f"  {level}: {count}")

        # Show error messages
        if error_lines:
            result.append(f"\nErrors ({len(error_lines)}):")
            max_errors = 10
            result.extend(error_lines[:max_errors])
            if len(error_lines) > max_errors:
                result.append(f"  ... ({len(error_lines) - max_errors} more)")

        return "\n".join(result)

    def _extract_level(self, obj: dict) -> str:
        """Extract log level from a JSON log entry."""
        for key in _LEVEL_KEYS:
            if key in obj:
                val = str(obj[key]).lower().strip()
                return val
        # Fallback: look for common patterns in message
        msg = self._extract_message(obj)
        if msg:
            if re.search(r"\b(ERROR|FATAL|PANIC)\b", msg):
                return "error"
            if re.search(r"\bWARN(ING)?\b", msg):
                return "warn"
        return "unknown"

    def _extract_message(self, obj: dict) -> str:
        """Extract message from a JSON log entry."""
        for key in _MESSAGE_KEYS:
            if key in obj:
                val = str(obj[key])
                if len(val) > 200:
                    val = val[:197] + "..."
                return val
        return ""
