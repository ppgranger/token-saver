"""Search output processor: grep -r, rg, ag."""

import re
from collections import defaultdict

from .base import Processor


class SearchProcessor(Processor):
    priority = 35
    hook_patterns = [
        r"^(grep|rg|ag)\b",
    ]

    @property
    def name(self) -> str:
        return "search"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(grep|rg|ag)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) < 20:
            return output

        # Detect format: file:line:content or file:content or just file
        by_file: dict[str, list[str]] = defaultdict(list)
        plain_matches = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Skip binary file warnings
            if re.match(r"^Binary file .* matches", stripped):
                continue

            # file:line:content or file:content
            m = re.match(r"^(.+?):(\d+:)?(.*)$", stripped)
            if (m and "/" in m.group(1)) or "." in m.group(1):
                filepath = m.group(1)
                content = stripped
                by_file[filepath].append(content)
            else:
                plain_matches.append(stripped)

        if not by_file and not plain_matches:
            return output

        total_matches = sum(len(v) for v in by_file.values()) + len(plain_matches)
        total_files = len(by_file)

        if total_files == 0:
            # Plain list of matches — just truncate
            if len(plain_matches) > 30:
                result = plain_matches[:25]
                result.append(f"... ({len(plain_matches) - 25} more matches)")
                return "\n".join(result)
            return output

        max_per_file = 3
        max_files = 20

        result = [f"{total_matches} matches across {total_files} files:"]

        sorted_files = sorted(by_file.items(), key=lambda x: -len(x[1]))
        for filepath, matches in sorted_files[:max_files]:
            count = len(matches)
            if count > max_per_file:
                result.append(f"{filepath}: ({count} matches)")
                for m in matches[:max_per_file]:
                    # Strip the filepath prefix to avoid repetition
                    display = m
                    if display.startswith(filepath + ":"):
                        display = "  " + display[len(filepath) + 1 :]
                    else:
                        display = "  " + display
                    result.append(display)
                result.append(f"  ... ({count - max_per_file} more)")
            else:
                for m in matches:
                    result.append(m)

        if total_files > max_files:
            result.append(f"... ({total_files - max_files} more files)")

        return "\n".join(result)
