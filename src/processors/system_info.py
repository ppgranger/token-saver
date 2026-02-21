"""System info processor: du, wc, df."""

import re

from .base import Processor


class SystemInfoProcessor(Processor):
    priority = 36
    hook_patterns = [
        r"^(wc|du|df)(\s|$)",
    ]

    @property
    def name(self) -> str:
        return "system_info"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(du|wc|df)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if re.search(r"\bdu\b", command):
            return self._process_du(output)
        if re.search(r"\bwc\b", command):
            return self._process_wc(output)
        if re.search(r"\bdf\b", command):
            return self._process_df(output)
        return output

    def _process_du(self, output: str) -> str:
        """Compress du: sort by size, top entries + total."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        entries = []
        total_line = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Detect total line (last line or "total" keyword)
            m = re.match(r"^([\d.]+\s*[KMGTP]?i?B?)\s+(.+)$", stripped)
            if not m:
                # Try tab-separated format
                parts = stripped.split("\t")
                if len(parts) == 2:
                    entries.append((parts[0].strip(), parts[1].strip()))
                continue
            size = m.group(1)
            path = m.group(2)
            if path in (".", "total"):
                total_line = stripped
            else:
                entries.append((size, path))

        if not entries:
            return output

        # Sort by size (parse numeric value for sorting)
        def parse_size(size_str: str) -> float:
            s = size_str.strip()
            multipliers = {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15}
            m = re.match(r"^([\d.]+)\s*([KMGTP])?", s)
            if m:
                val = float(m.group(1))
                if m.group(2):
                    val *= multipliers.get(m.group(2), 1)
                return val
            try:
                return float(s)
            except ValueError:
                return 0

        entries.sort(key=lambda x: parse_size(x[0]), reverse=True)

        result = []
        for size, path in entries[:15]:
            result.append(f"  {size}\t{path}")
        if len(entries) > 15:
            result.append(f"  ... ({len(entries) - 15} more entries)")
        if total_line:
            result.append(total_line)

        return "\n".join(result)

    def _process_wc(self, output: str) -> str:
        """Compress wc: sort by count, top entries + total."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        entries = []
        total_line = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                if parts[-1] == "total":
                    total_line = stripped
                else:
                    try:
                        count = int(parts[0])
                        entries.append((count, stripped))
                    except ValueError:
                        entries.append((0, stripped))

        if not entries:
            return output

        entries.sort(key=lambda x: x[0], reverse=True)

        # Filter zero entries
        non_zero = [(c, line) for c, line in entries if c > 0]
        zero_count = len(entries) - len(non_zero)

        result = []
        for _, line in non_zero[:15]:
            result.append(f"  {line}")
        if len(non_zero) > 15:
            result.append(f"  ... ({len(non_zero) - 15} more)")
        if zero_count > 0:
            result.append(f"  ({zero_count} entries with count 0)")
        if total_line:
            result.append(total_line)

        return "\n".join(result)

    def _strip_filesystem_column(self, lines: list[str]) -> list[str]:
        """Remove the Filesystem (device) column from df output."""
        if not lines:
            return lines
        header = lines[0]
        # Find where "Size" starts — everything before is the Filesystem column
        m = re.search(r"\bSize\b", header)
        if not m:
            return lines
        col_end = m.start()
        if col_end == 0:
            return lines
        return [line[col_end:] if len(line) > col_end else line for line in lines]

    def _process_df(self, output: str) -> str:
        """Compress df: strip snap/loop/tmpfs mounts and Filesystem column."""
        lines = output.splitlines()

        result = []
        filtered_count = 0
        for line in lines:
            stripped = line.strip()
            # Skip snap/loop mounts
            if re.search(r"\b(snap|loop\d*|squashfs)\b", stripped):
                continue
            # Skip tmpfs unless it's /tmp
            if re.match(r"^tmpfs\b", stripped) and "/tmp" not in stripped:  # noqa: S108
                filtered_count += 1
                continue
            # Skip devtmpfs
            if re.match(r"^devtmpfs\b", stripped):
                filtered_count += 1
                continue
            result.append(line)

        # Strip Filesystem column (device paths are noise for LLM)
        result = self._strip_filesystem_column(result)

        if filtered_count > 0:
            result.append(f"({filtered_count} system mounts hidden)")

        return "\n".join(result)
