"""Generic fallback processor: ANSI strip, dedup, whitespace collapse, truncation."""

import re

from .. import config
from .base import Processor

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")

# Regex to normalize numbers/percentages for fuzzy matching
_NUMERIC_RE = re.compile(r"\d+(\.\d+)?")
# Progress bar visual characters
_PROGRESS_BAR_RE = re.compile(r"[━█▓░▒■□●○#=\->]{5,}")


class GenericProcessor(Processor):
    """Fallback processor that applies universal compression heuristics."""

    priority = 999
    hook_patterns = []

    @property
    def name(self) -> str:
        return "generic"

    def can_handle(self, command: str) -> bool:
        return True  # Always matches as fallback

    def process(self, command: str, output: str) -> str:
        lines = output.splitlines()
        lines = self._strip_ansi(lines)
        lines = self._strip_progress_bars(lines)
        lines = self._collapse_blank_lines(lines)
        lines = self._collapse_repeated_lines(lines)
        lines = self._collapse_similar_lines(lines)
        lines = self._strip_trailing_whitespace(lines)
        threshold = config.get("generic_truncate_threshold")
        if len(lines) > threshold:
            lines = self._truncate_middle(lines)
        return "\n".join(lines)

    def clean(self, text: str) -> str:
        """Light cleanup pass: ANSI strip and blank line collapse only.

        Used by the engine after a specialized processor to sanitize output
        without applying heavy dedup or truncation.
        """
        lines = text.splitlines()
        lines = self._strip_ansi(lines)
        lines = self._collapse_blank_lines(lines)
        lines = self._strip_trailing_whitespace(lines)
        return "\n".join(lines)

    def _strip_ansi(self, lines: list[str]) -> list[str]:
        return [ANSI_RE.sub("", line) for line in lines]

    def _strip_trailing_whitespace(self, lines: list[str]) -> list[str]:
        return [line.rstrip() for line in lines]

    def _strip_progress_bars(self, lines: list[str]) -> list[str]:
        """Remove lines that are purely progress bars or spinners."""
        result = []
        for line in lines:
            stripped = line.strip()
            # Pure progress bar lines (>60% bar characters)
            if stripped and _PROGRESS_BAR_RE.search(stripped):
                bar_match = _PROGRESS_BAR_RE.search(stripped)
                if bar_match and len(bar_match.group(0)) > len(stripped) * 0.5:
                    continue
            # Spinner lines
            if stripped in (
                "⠋",
                "⠙",
                "⠹",
                "⠸",
                "⠼",
                "⠴",
                "⠦",
                "⠧",
                "⠇",
                "⠏",
                "⣾",
                "⣽",
                "⣻",
                "⢿",
                "⡿",
                "⣟",
                "⣯",
                "⣷",
            ):
                continue
            result.append(line)
        return result

    def _collapse_blank_lines(self, lines: list[str]) -> list[str]:
        """Merge consecutive blank lines into one."""
        result = []
        prev_blank = False
        for line in lines:
            is_blank = line.strip() == ""
            if is_blank and prev_blank:
                continue
            result.append(line)
            prev_blank = is_blank
        return result

    def _collapse_repeated_lines(self, lines: list[str]) -> list[str]:
        """Collapse consecutive identical lines into `line (xN)`."""
        if not lines:
            return lines
        result = []
        current = lines[0]
        count = 1
        for line in lines[1:]:
            if line == current and current.strip():
                count += 1
            else:
                self._flush(result, current, count)
                current = line
                count = 1
        self._flush(result, current, count)
        return result

    def _collapse_similar_lines(self, lines: list[str]) -> list[str]:
        """Collapse consecutive lines that differ only in numbers/percentages.

        Only applies to lines where >=30% of the content is numeric — this
        targets progress output (curl, wget, download bars) while preserving
        data lines where numbers are meaningful identifiers.
        """
        if not lines:
            return lines
        result = []
        current = lines[0]
        current_normalized = self._normalize_numbers(current)
        group: list[str] = [current]

        for line in lines[1:]:
            normalized = self._normalize_numbers(line)
            if (
                normalized == current_normalized
                and current.strip()
                and len(current.strip()) > 10
                and self._is_numeric_heavy(current)
            ):
                group.append(line)
            else:
                self._flush_similar(result, group)
                current = line
                current_normalized = normalized
                group = [line]

        self._flush_similar(result, group)
        return result

    def _normalize_numbers(self, line: str) -> str:
        """Replace all numbers with a placeholder for fuzzy comparison."""
        return _NUMERIC_RE.sub("N", line.strip())

    def _is_numeric_heavy(self, line: str) -> bool:
        """Check if a line is progress/status output where numbers are noise.

        Returns True for lines where numeric changes are not meaningful data,
        such as progress bars, download stats, and transfer indicators.
        """
        stripped = line.strip()
        if not stripped:
            return False
        # Count digits + common numeric-adjacent chars (colons for time, dashes for ETA)
        numeric_chars = sum(1 for c in stripped if c.isdigit())
        if numeric_chars / len(stripped) >= 0.25:
            return True
        # Percentage patterns
        if re.search(r"\d+(\.\d+)?%", stripped):
            return True
        # Transfer rate patterns
        if re.search(r"\d+(\.\d+)?\s*(KB|MB|GB|B|kB|MiB|GiB|k|M|G)/s", stripped):
            return True
        # ETA/time remaining patterns
        if re.search(r"(ETA|eta)\s+\d+", stripped):
            return True
        # Curl/wget progress format: lines with --:--:-- time patterns
        if re.search(r"--:--:--|(\d+:){2}\d+", stripped) and numeric_chars >= 5:
            return True
        # Lines that are mostly whitespace + numbers (tabular numeric output)
        non_ws = stripped.replace(" ", "")
        return bool(non_ws and sum(1 for c in non_ws if c.isdigit()) / len(non_ws) >= 0.40)

    def _flush(self, result: list[str], line: str, count: int) -> None:
        if count > 1:
            result.append(f"{line} (x{count})")
        else:
            result.append(line)

    def _flush_similar(self, result: list[str], group: list[str]) -> None:
        count = len(group)
        if count >= 5:
            result.append(group[0])
            result.append(f"  ... ({count - 2} similar lines)")
            result.append(group[-1])
        else:
            result.extend(group)

    def _truncate_middle(self, lines: list[str]) -> list[str]:
        """Truncate middle of long output."""
        keep_head = config.get("generic_keep_head")
        keep_tail = config.get("generic_keep_tail")
        total = len(lines)
        removed = total - keep_head - keep_tail
        return [
            *lines[:keep_head],
            f"\n... ({removed} lines truncated, {total} total) ...\n",
            *lines[-keep_tail:],
        ]
