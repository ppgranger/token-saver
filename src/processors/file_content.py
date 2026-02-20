"""File content processor: content-aware compression for long file outputs."""

import json
import re

from .. import config
from .base import Processor

# Extension sets for content type detection
_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".swift",
    ".scala",
    ".tf",
    ".hcl",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".lua",
    ".r",
    ".m",
    ".cs",
    ".vb",
    ".pl",
    ".pm",
    ".ex",
    ".exs",
    ".hs",
    ".ml",
    ".vue",
    ".svelte",
    ".dart",
    ".zig",
    ".nim",
    ".v",
    ".groovy",
    ".sql",
    ".md",
    ".rst",
}

_CONFIG_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".env",
    ".properties",
    ".plist",
    ".conf",
}

_CSV_EXTENSIONS = {".csv", ".tsv"}

# Regex patterns for code definitions, grouped by language family
_DEFINITION_PATTERNS = [
    # Python
    re.compile(r"^\s*(async\s+)?def\s+\w+"),
    re.compile(r"^\s*class\s+\w+"),
    # JS/TS
    re.compile(r"^\s*(export\s+)?(async\s+)?function\s+\w+"),
    re.compile(r"^\s*(export\s+)?(default\s+)?class\s+\w+"),
    re.compile(r"^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?\(.*\)\s*=>"),
    re.compile(r"^\s*(export\s+)?interface\s+\w+"),
    re.compile(r"^\s*(export\s+)?type\s+\w+\s*="),
    re.compile(r"^\s*(export\s+)?enum\s+\w+"),
    # Go
    re.compile(r"^\s*func\s+(\(.*?\)\s*)?\w+"),
    re.compile(r"^\s*type\s+\w+\s+(struct|interface)"),
    # Rust
    re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+\w+"),
    re.compile(r"^\s*(pub\s+)?struct\s+\w+"),
    re.compile(r"^\s*(pub\s+)?enum\s+\w+"),
    re.compile(r"^\s*(pub\s+)?trait\s+\w+"),
    re.compile(r"^\s*impl\s+"),
    # Java/Kotlin/C#
    re.compile(r"^\s*(public|private|protected|internal)\s+.*\s+(class|interface|enum)\s+\w+"),
    re.compile(
        r"^\s*(public|private|protected|internal)"
        r"\s+(static\s+)?(async\s+)?\w+[\w<>\[\],\s]*\s+\w+\s*\("
    ),
    # C/C++ -- require a return type keyword or modifier before the function name
    re.compile(
        r"^\s*(static\s+|extern\s+|inline\s+|virtual\s+|const\s+)*"
        r"(void|int|char|float|double|long|short|unsigned|signed|bool|auto|size_t|"
        r"std::\w+|struct\s+\w+|enum\s+\w+|class\s+\w+|\w+_t)"
        r"[\s\*&]+\w+\s*\("
    ),
    # Ruby
    re.compile(r"^\s*def\s+\w+"),
    re.compile(r"^\s*class\s+\w+"),
    re.compile(r"^\s*module\s+\w+"),
    # PHP
    re.compile(r"^\s*(public|private|protected)?\s*(static\s+)?function\s+\w+"),
    # Shell
    re.compile(r"^\s*\w+\s*\(\)\s*\{"),
    re.compile(r"^\s*function\s+\w+"),
]

# Important markers to always preserve in code
_IMPORTANT_MARKERS = re.compile(r"\b(TODO|FIXME|HACK|BUG|XXX|NOQA|SAFETY)\b", re.IGNORECASE)

# Log level patterns
_LOG_LEVEL_RE = re.compile(
    r"("
    r"\d{4}[-/]\d{2}[-/]\d{2}"  # date
    r"|^\d{2}:\d{2}:\d{2}"  # time
    r"|\[(INFO|DEBUG|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE)\]"
    r"|\b(INFO|DEBUG|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE)\s"
    r"|^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"  # syslog date
    r")",
    re.IGNORECASE,
)

_LOG_ERROR_RE = re.compile(
    r"\b(ERROR|FATAL|CRITICAL|PANIC|EXCEPTION)\b"
    r"|\bWARN(ING)?\b"
    r"|\[(ERROR|FATAL|CRITICAL|WARN|WARNING)\]",
    re.IGNORECASE,
)


class FileContentProcessor(Processor):
    priority = 51
    hook_patterns = [
        r"^(cat|head|tail|less|more|bat)\b",
    ]

    @property
    def name(self) -> str:
        return "file_content"

    def can_handle(self, command: str) -> bool:
        return bool(re.match(r".*\b(cat|head|tail|less|more|bat)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        max_lines = config.get("max_file_lines")

        if len(lines) <= max_lines:
            return output

        ext = self._extract_extension(command)
        content_type = self._detect_type(ext, lines)

        if content_type == "code":
            return self._compress_code(lines, ext)
        elif content_type == "config":
            return self._compress_config(lines, ext)
        elif content_type == "log":
            return self._compress_log(lines)
        elif content_type == "csv":
            return self._compress_csv(lines)
        else:
            return self._truncate_default(lines)

    # ── Type detection ──────────────────────────────────────────────

    def _extract_extension(self, command: str) -> str:
        """Extract file extension from the command, e.g. 'cat foo.py' → '.py'."""
        match = re.search(r"[\w/\\.-]+\.(\w+)(?:\s|$|;|\||&)", command)
        if match:
            return "." + match.group(1).lower()
        return ""

    def _detect_type(self, ext: str, lines: list[str]) -> str:
        """Detect content type from extension, then heuristics."""
        if ext in _CODE_EXTENSIONS:
            return "code"
        if ext in _CONFIG_EXTENSIONS:
            return "config"
        if ext in _CSV_EXTENSIONS:
            return "csv"

        # Heuristic: log detection (>30% lines match log patterns)
        sample = lines[:200]
        log_matches = sum(1 for line in sample if _LOG_LEVEL_RE.search(line))
        if log_matches > len(sample) * 0.3:
            return "log"

        # Heuristic: JSON (starts with { or [)
        stripped_start = output_start(lines)
        if stripped_start in ("{", "["):
            return "config"

        # Heuristic: CSV (consistent comma/tab separators in first lines)
        if self._looks_like_csv(lines[:10]):
            return "csv"

        return "unknown"

    def _looks_like_csv(self, sample: list[str]) -> bool:
        """Check if lines look like CSV/TSV data."""
        if len(sample) < 3:
            return False
        for sep in (",", "\t"):
            counts = [line.count(sep) for line in sample if line.strip()]
            if len(counts) >= 3 and counts[0] >= 2 and all(c == counts[0] for c in counts[:5]):
                return True
        return False

    # ── Code compression ────────────────────────────────────────────

    def _compress_code(self, lines: list[str], ext: str) -> str:
        total = len(lines)
        head_lines = config.get("file_code_head_lines")
        body_lines = config.get("file_code_body_lines")

        result = []
        # Keep header (imports, shebang, module docstrings)
        result.extend(lines[:head_lines])

        # Scan rest for definitions and important markers
        i = head_lines
        definitions_found = 0
        last_added = head_lines - 1
        omitted_count = 0

        while i < total:
            line = lines[i]

            # Check if this line is a definition
            is_def = any(p.match(line) for p in _DEFINITION_PATTERNS)
            is_important = bool(_IMPORTANT_MARKERS.search(line))

            if is_def:
                definitions_found += 1
                # Add separator if we skipped lines
                gap = i - last_added - 1
                if gap > 0:
                    omitted_count += gap
                    result.append(f"  ... ({gap} lines omitted)")

                # Add the definition signature + a few body lines
                result.append(line)
                end = min(i + 1 + body_lines, total)
                for j in range(i + 1, end):
                    result.append(lines[j])
                last_added = end - 1
                i = end
                continue

            if is_important:
                gap = i - last_added - 1
                if gap > 0:
                    omitted_count += gap
                    result.append(f"  ... ({gap} lines omitted)")
                result.append(line)
                last_added = i

            i += 1

        # Account for any trailing omitted lines
        trailing_gap = total - last_added - 1
        if trailing_gap > 0:
            omitted_count += trailing_gap
            result.append(f"  ... ({trailing_gap} lines omitted)")

        result.append(
            f"\n({total} total lines, {definitions_found} definitions found, "
            f"{omitted_count} lines omitted)"
        )
        return "\n".join(result)

    # ── Config compression ──────────────────────────────────────────

    def _compress_config(self, lines: list[str], ext: str) -> str:
        total = len(lines)
        raw = "\n".join(lines)

        if ext == ".json":
            return self._compress_json(raw, total)
        elif ext in (".yaml", ".yml"):
            return self._compress_yaml(lines, total)
        elif ext == ".xml":
            return self._compress_xml(lines, total)
        else:
            # TOML, INI, CFG, ENV, properties — keep section headers and keys
            return self._compress_ini_like(lines, total)

    def _compress_json(self, raw: str, total: int) -> str:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._truncate_default(raw.splitlines())

        result = self._summarize_json_value(data, depth=0, max_depth=2)
        return f"{result}\n\n({total} total lines)"

    def _summarize_json_value(self, val, depth: int, max_depth: int) -> str:
        indent = "  " * depth
        if isinstance(val, dict):
            if depth >= max_depth:
                return f"{{{len(val)} keys}}"
            items = []
            for k, v in val.items():
                summarized = self._summarize_json_value(v, depth + 1, max_depth)
                items.append(f'{indent}  "{k}": {summarized}')
            return "{\n" + ",\n".join(items) + f"\n{indent}}}"
        elif isinstance(val, list):
            if len(val) == 0:
                return "[]"
            if len(val) <= 3:
                inner = [self._summarize_json_value(v, depth + 1, max_depth) for v in val]
                return "[" + ", ".join(inner) + "]"
            first_three = [self._summarize_json_value(v, depth + 1, max_depth) for v in val[:3]]
            return "[" + ", ".join(first_three) + f", ... ({len(val)} items total)]"
        elif isinstance(val, str):
            if len(val) > 100:
                return f'"{val[:80]}..." ({len(val)} chars)'
            return json.dumps(val)
        else:
            return json.dumps(val)

    def _compress_yaml(self, lines: list[str], total: int) -> str:
        result = []
        nested_count = 0
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            # Keep top-level keys (indent 0) and second-level (indent <= 2)
            if indent <= 2 and stripped and not stripped.startswith("#"):
                # Truncate long values
                if ": " in stripped and len(stripped) > 120:
                    key_part = stripped.split(": ", 1)[0]
                    result.append(f"{line[:indent]}{key_part}: ... (truncated)")
                else:
                    result.append(line)
            else:
                nested_count += 1

        if nested_count > 0:
            result.append(f"\n  ... ({nested_count} nested lines omitted)")
        result.append(f"\n({total} total lines)")
        return "\n".join(result)

    def _compress_xml(self, lines: list[str], total: int) -> str:
        result = []
        nested_count = 0
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            # Keep XML declaration, top-level and second-level tags
            if indent <= 4 or stripped.startswith(("<?", "<!")):
                result.append(line)
            else:
                nested_count += 1

        if nested_count > 0:
            result.append(f"  ... ({nested_count} nested lines omitted)")
        result.append(f"\n({total} total lines)")
        return "\n".join(result)

    def _compress_ini_like(self, lines: list[str], total: int) -> str:
        result = []
        nested_count = 0
        for line in lines:
            stripped = line.strip()
            # Keep section headers, key=value lines at top level, and comments
            if stripped.startswith(("[", "#", ";")) or "=" in stripped or ":" in stripped:
                if len(stripped) > 120:
                    key_part = re.split(r"[=:]", stripped, maxsplit=1)[0]
                    result.append(f"{key_part}= ... (truncated)")
                else:
                    result.append(line)
            elif stripped:
                nested_count += 1

        if nested_count > 0:
            result.append(f"  ... ({nested_count} additional lines omitted)")
        result.append(f"\n({total} total lines)")
        return "\n".join(result)

    # ── Log compression ─────────────────────────────────────────────

    def _compress_log(self, lines: list[str]) -> str:
        total = len(lines)
        context_lines = config.get("file_log_context_lines")

        # Keep first 5 and last 5 for temporal context
        head = lines[:5]
        tail = lines[-5:]

        # Scan middle for ERROR/WARN/FATAL lines
        middle = lines[5:-5] if len(lines) > 10 else []
        error_indices = set()
        info_count = 0
        debug_count = 0

        for idx, line in enumerate(middle):
            if _LOG_ERROR_RE.search(line):
                # Add this line + context
                for c in range(idx - context_lines, idx + context_lines + 1):
                    if 0 <= c < len(middle):
                        error_indices.add(c)
            elif re.search(r"\bDEBUG\b", line, re.IGNORECASE):
                debug_count += 1
            elif re.search(r"\bINFO\b", line, re.IGNORECASE):
                info_count += 1

        # Build result
        result = head[:]
        if middle:
            if error_indices:
                result.append(f"\n... (scanning {len(middle)} middle lines) ...\n")
                sorted_indices = sorted(error_indices)
                prev = -2
                for idx in sorted_indices:
                    if idx > prev + 1:
                        gap = idx - prev - 1
                        if prev >= 0:
                            result.append(f"  ... ({gap} lines skipped)")
                    result.append(middle[idx])
                    prev = idx
                remaining = len(middle) - 1 - prev
                if remaining > 0:
                    result.append(f"  ... ({remaining} lines skipped)")
            else:
                result.append(f"\n... ({len(middle)} lines, no errors/warnings found) ...\n")

        omitted_parts = []
        if info_count > 0:
            omitted_parts.append(f"{info_count} INFO")
        if debug_count > 0:
            omitted_parts.append(f"{debug_count} DEBUG")
        other = len(middle) - len(error_indices) - info_count - debug_count
        if other > 0:
            omitted_parts.append(f"{other} other")

        result.extend(tail)
        summary = ", ".join(omitted_parts) + " lines omitted" if omitted_parts else ""
        result.append(f"\n({total} total lines{'; ' + summary if summary else ''})")
        return "\n".join(result)

    # ── CSV compression ─────────────────────────────────────────────

    def _compress_csv(self, lines: list[str]) -> str:
        total = len(lines)
        head_rows = config.get("file_csv_head_rows")
        tail_rows = config.get("file_csv_tail_rows")

        # Detect number of columns from header
        header = lines[0] if lines else ""
        sep = "\t" if "\t" in header else ","
        col_count = header.count(sep) + 1

        # header + head data rows + tail data rows
        result = [lines[0]]  # header
        data_lines = lines[1:]

        if len(data_lines) <= head_rows + tail_rows:
            return output_join(lines)

        result.extend(data_lines[:head_rows])
        omitted = len(data_lines) - head_rows - tail_rows
        result.append(f"... ({omitted} rows omitted)")
        result.extend(data_lines[-tail_rows:])
        result.append(f"\n({total - 1} data rows, {col_count} columns)")
        return "\n".join(result)

    # ── Fallback: original head/tail truncation ─────────────────────

    def _truncate_default(self, lines: list[str]) -> str:
        keep_head = config.get("file_keep_head")
        keep_tail = config.get("file_keep_tail")
        total = len(lines)
        truncated = total - keep_head - keep_tail

        result = [
            *lines[:keep_head],
            f"\n... ({truncated} lines truncated, {total} total lines) ...\n",
            *lines[-keep_tail:],
        ]
        return "\n".join(result)


# ── Helpers ──────────────────────────────────────────────────────────


def output_start(lines: list[str]) -> str:
    """Return the first non-whitespace character of the output."""
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped[0]
    return ""


def output_join(lines: list[str]) -> str:
    """Join lines back into output string."""
    return "\n".join(lines)
