"""Database query output processor: psql, mysql, sqlite3."""

import re

from .. import config
from .base import Processor

_DB_CMD_RE = re.compile(r"\b(psql|mysql|sqlite3|mycli|pgcli|litecli)\b")


class DbQueryProcessor(Processor):
    priority = 38
    hook_patterns = [
        r"^(psql|mysql|sqlite3|mycli|pgcli|litecli)\b",
    ]

    @property
    def name(self) -> str:
        return "db_query"

    def can_handle(self, command: str) -> bool:
        return bool(_DB_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()

        # Detect output format
        if self._is_psql_table(lines):
            return self._process_psql_table(lines)
        if self._is_mysql_table(lines):
            return self._process_mysql_table(lines)
        if self._is_csv_output(lines):
            return self._process_csv(lines)

        # Fallback: generic row truncation for any tabular output
        if len(lines) > 30:
            return self._truncate_rows(lines)

        return output

    def _is_psql_table(self, lines: list[str]) -> bool:
        """Detect PostgreSQL-style table output with ─ or - separators."""
        if len(lines) < 3:
            return False
        # psql uses lines like "----+----" or "────┼────" as separators
        for line in lines[:5]:
            if re.match(r"^[-─┼+|]+$", line.strip()):
                return True
            # Also detect the header underline pattern: " col1 | col2 "
            if "|" in line and re.search(r"\w", line):
                return True
        return False

    def _is_mysql_table(self, lines: list[str]) -> bool:
        """Detect MySQL-style table output with +---+ borders."""
        if len(lines) < 3:
            return False
        return bool(re.match(r"^\+[-+]+\+$", lines[0].strip()))

    def _is_csv_output(self, lines: list[str]) -> bool:
        """Detect CSV/TSV output (e.g., psql -A or sqlite3 with .mode csv)."""
        if len(lines) < 3:
            return False
        for sep in (",", "\t", "|"):
            counts = [line.count(sep) for line in lines[:5] if line.strip()]
            if len(counts) >= 3 and counts[0] >= 1 and all(c == counts[0] for c in counts):
                return True
        return False

    def _process_psql_table(self, lines: list[str]) -> str:
        """Compress PostgreSQL table output: keep header + limited rows."""
        # Find header and separator
        header_end = 0
        for i, line in enumerate(lines[:5]):
            if re.match(r"^[-─┼+]+$", line.strip()):
                header_end = i + 1
                break

        if header_end == 0:
            header_end = 1

        # Find footer (row count line like "(42 rows)")
        footer_lines = []
        data_end = len(lines)
        for i in range(len(lines) - 1, max(0, len(lines) - 5), -1):
            stripped = lines[i].strip()
            if re.match(r"^\(\d+\s+rows?\)$", stripped):
                footer_lines = [lines[i]]
                data_end = i
                break
            if re.match(r"^Time:\s+", stripped):
                footer_lines.insert(0, lines[i])
                data_end = i

        data_lines = lines[header_end:data_end]
        # Filter out separator lines from data
        data_lines = [
            row for row in data_lines
            if not re.match(r"^[-─┼+]+$", row.strip())
        ]

        max_rows = config.get("db_max_rows") if config.get("db_max_rows") else 20
        head_rows = max_rows // 2 + max_rows % 2
        tail_rows = max_rows // 2

        if len(data_lines) <= max_rows:
            return "\n".join(lines)

        result = lines[:header_end]
        result.extend(data_lines[:head_rows])
        omitted = len(data_lines) - head_rows - tail_rows
        result.append(f"  ... ({omitted} rows omitted)")
        result.extend(data_lines[-tail_rows:])
        result.extend(footer_lines)

        return "\n".join(result)

    def _process_mysql_table(self, lines: list[str]) -> str:
        """Compress MySQL table output: keep header + limited rows."""
        # MySQL format: +---+---+, | col | col |, +---+---+, | data |, ..., +---+---+
        # Find header section (border + header + border)
        header_section = []
        data_lines = []
        footer_lines = []
        phase = "header"

        border_count = 0
        for line in lines:
            stripped = line.strip()
            if re.match(r"^\+[-+]+\+$", stripped):
                border_count += 1
                if border_count <= 2:
                    header_section.append(line)
                    if border_count == 2:
                        phase = "data"
                else:
                    footer_lines.append(line)
            elif phase == "header":
                header_section.append(line)
            elif phase == "data":
                if re.match(r"^\d+\s+rows?\s+in\s+set", stripped):
                    footer_lines.append(line)
                else:
                    data_lines.append(line)

        max_rows = config.get("db_max_rows") if config.get("db_max_rows") else 20
        head_rows = max_rows // 2 + max_rows % 2
        tail_rows = max_rows // 2

        if len(data_lines) <= max_rows:
            return "\n".join(lines)

        result = header_section
        result.extend(data_lines[:head_rows])
        omitted = len(data_lines) - head_rows - tail_rows
        result.append(f"| ... ({omitted} rows omitted)")
        result.extend(data_lines[-tail_rows:])
        result.extend(footer_lines)

        return "\n".join(result)

    def _process_csv(self, lines: list[str]) -> str:
        """Compress CSV/delimited output: keep header + limited rows."""
        if len(lines) <= 20:
            return "\n".join(lines)

        header = lines[0]
        data = lines[1:]

        # Detect separator from header
        sep = ","
        for s in ("\t", "|", ","):
            if s in header:
                sep = s
                break
        col_count = header.count(sep) + 1

        head_rows = 10
        tail_rows = 5

        if len(data) <= head_rows + tail_rows:
            return "\n".join(lines)

        result = [header]
        result.extend(data[:head_rows])
        omitted = len(data) - head_rows - tail_rows
        result.append(f"... ({omitted} rows omitted)")
        result.extend(data[-tail_rows:])
        result.append(f"\n({len(data)} data rows, {col_count} columns)")

        return "\n".join(result)

    def _truncate_rows(self, lines: list[str]) -> str:
        """Generic row truncation for unrecognized tabular output."""
        if len(lines) <= 30:
            return "\n".join(lines)

        # Keep first 15 and last 5 lines
        result = lines[:15]
        result.append(f"... ({len(lines) - 20} rows omitted)")
        result.extend(lines[-5:])
        return "\n".join(result)
