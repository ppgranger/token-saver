"""File content processor: content-aware compression for file outputs.

Strategy — strict two-category dispatch:

NEVER COMPRESS (pass-through):
  Source code and sensitive config files. The model reads these to write
  patches and understand exact values.  One missing line → wrong patch.

COMPRESS (structure-preserving):
  Data/structured files the model reads for information, not patching:
  JSON, YAML, TOML, XML, logs, CSV, lock files, docs, unknown types.
"""

import json
import re

from .. import config
from .base import Processor

# ── File type sets ───────────────────────────────────────────────────

# Source code: NEVER compressed — model needs exact content for patching
_SOURCE_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".scala",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".ex",
    ".exs",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".lua",
    ".r",
    ".m",
    ".vb",
    ".pl",
    ".pm",
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
    ".tf",
    ".hcl",
}

# Config files with exact values: NEVER compressed
_SENSITIVE_CONFIG_EXTENSIONS = {
    ".env",
    ".ini",
    ".cfg",
    ".conf",
}

# Lock files: AGGRESSIVELY compressed (dependency names + versions only)
_LOCK_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    "bun.lockb",
}

# Structured data: compress preserving keys + structure
_STRUCTURED_EXTENSIONS = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
}

# Log files
_LOG_EXTENSIONS = {".log"}

# CSV/TSV files
_CSV_EXTENSIONS = {".csv", ".tsv"}

# Documentation
_DOC_EXTENSIONS = {".md", ".rst"}

# Log level patterns
_LOG_LEVEL_RE = re.compile(
    r"("
    r"\d{4}[-/]\d{2}[-/]\d{2}"
    r"|^\d{2}:\d{2}:\d{2}"
    r"|\[(INFO|DEBUG|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE)\]"
    r"|\b(INFO|DEBUG|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE)\s"
    r"|^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"
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
        return bool(re.search(r"\b(cat|head|tail|less|more|bat)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        ext = self._extract_extension(command)
        filename = self._extract_filename(command)

        # ── NEVER COMPRESS: source code ──────────────────────────────
        if ext in _SOURCE_CODE_EXTENSIONS:
            return output

        # ── NEVER COMPRESS: sensitive config ─────────────────────────
        if ext in _SENSITIVE_CONFIG_EXTENSIONS:
            return output

        # Below here: only compress if the output is long enough
        lines = output.splitlines()
        max_lines = config.get("max_file_lines")

        if len(lines) <= max_lines:
            return output

        # ── Lock files: aggressive compression ───────────────────────
        if filename in _LOCK_FILENAMES:
            return self._compress_lock_file(lines, ext, filename)

        # ── Structured data: preserve keys + structure ───────────────
        structured_type = _STRUCTURED_EXTENSIONS.get(ext)
        if structured_type:
            return self._compress_structured(lines, structured_type)

        # ── Log files ────────────────────────────────────────────────
        if ext in _LOG_EXTENSIONS:
            return self._compress_log(lines)

        # ── CSV/TSV ──────────────────────────────────────────────────
        if ext in _CSV_EXTENSIONS:
            return self._compress_csv(lines)

        # ── Documentation ────────────────────────────────────────────
        if ext in _DOC_EXTENSIONS:
            return self._truncate_default(lines)

        # ── Heuristic detection for extensionless/unknown files ──────
        detected = self._detect_heuristic(lines)
        if detected == "log":
            return self._compress_log(lines)
        if detected == "json":
            return self._compress_structured(lines, "json")
        if detected == "csv":
            return self._compress_csv(lines)

        # ── Unknown: conservative generic compression ────────────────
        return self._truncate_default(lines)

    # ── Filename / extension extraction ──────────────────────────────

    def _extract_extension(self, command: str) -> str:
        """Extract file extension from the command, e.g. 'cat foo.py' -> '.py'.

        Also handles dotfiles like '.env' -> '.env'.
        """
        # Find the file argument (skip the command itself and flags)
        parts = command.split()
        for part in parts[1:]:
            if part.startswith("-"):
                continue
            # Get the basename
            basename = part.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            # Dotfile like .env
            if basename.startswith(".") and "." not in basename[1:]:
                return "." + basename[1:].lower()
            # Normal extension
            dot_pos = basename.rfind(".")
            if dot_pos > 0:
                return "." + basename[dot_pos + 1 :].lower()
        return ""

    def _extract_filename(self, command: str) -> str:
        """Extract bare filename from the command, e.g. 'cat /path/to/package-lock.json'."""
        parts = command.split()
        for part in parts[1:]:
            if part.startswith("-"):
                continue
            return part.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return ""

    # ── Heuristic detection (for extensionless files) ────────────────

    def _detect_heuristic(self, lines: list[str]) -> str:
        """Detect content type from content heuristics."""
        # Log detection (>30% lines match log patterns)
        sample = lines[:200]
        log_matches = sum(1 for line in sample if _LOG_LEVEL_RE.search(line))
        if log_matches > len(sample) * 0.3:
            return "log"

        # JSON (starts with { or [)
        first_char = _output_start(lines)
        if first_char in ("{", "["):
            return "json"

        # CSV (consistent separators)
        if self._looks_like_csv(lines[:10]):
            return "csv"

        return "unknown"

    def _looks_like_csv(self, sample: list[str]) -> bool:
        if len(sample) < 3:
            return False
        for sep in (",", "\t"):
            counts = [line.count(sep) for line in sample if line.strip()]
            if len(counts) >= 3 and counts[0] >= 2 and all(c == counts[0] for c in counts[:5]):
                return True
        return False

    # ── Lock file compression ────────────────────────────────────────

    def _compress_lock_file(self, lines: list[str], ext: str, filename: str) -> str:
        """Extract only dependency names and versions from lock files."""
        total = len(lines)
        raw = "\n".join(lines)

        if filename == "package-lock.json":
            return self._compress_npm_lock(raw, total)
        if filename in ("yarn.lock", "Gemfile.lock"):
            return self._compress_yarn_lock(lines, total)
        if filename == "poetry.lock":
            return self._compress_poetry_lock(lines, total)
        if filename == "Cargo.lock":
            return self._compress_cargo_lock(lines, total)
        if filename in ("composer.lock", "Pipfile.lock"):
            return self._compress_json_lock(raw, total)
        if filename == "go.sum":
            return self._compress_go_sum(lines, total)

        # Fallback for unrecognized lock files
        return self._truncate_default(lines)

    def _compress_npm_lock(self, raw: str, total: int) -> str:
        """package-lock.json: extract top-level dependency names + versions."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._truncate_default(raw.splitlines())

        deps = {}
        # lockfileVersion 3 uses "packages" with "" as root
        packages = data.get("packages", {})
        if packages:
            for path, info in packages.items():
                if not path or path == "":
                    continue
                # "node_modules/lodash" -> "lodash"
                name = path.rsplit("node_modules/", 1)[-1]
                version = info.get("version", "?")
                # Only top-level (no nested node_modules)
                if name.count("node_modules/") == 0:
                    deps[name] = version
        else:
            # lockfileVersion 1 uses "dependencies"
            for name, info in data.get("dependencies", {}).items():
                deps[name] = info.get("version", "?") if isinstance(info, dict) else "?"

        result = [f"package-lock.json ({len(deps)} dependencies, {total} lines):"]
        for name, version in sorted(deps.items()):
            result.append(f"  {name}@{version}")
        return "\n".join(result)

    def _compress_yarn_lock(self, lines: list[str], total: int) -> str:
        """yarn.lock / Gemfile.lock: extract package@version entries."""
        deps = []
        for line in lines:
            stripped = line.strip()
            # yarn: lines like '"lodash@^4.17.21":'  or  'lodash@^4.17.21:'
            if stripped and not stripped.startswith("#") and stripped.endswith(":"):
                name = stripped.rstrip(":").strip('"')
                deps.append(name)
            # version line
            if stripped.startswith("version "):
                version = stripped.split('"')[1] if '"' in stripped else stripped.split()[-1]
                if deps and "@" not in deps[-1].split(",")[0].rsplit("@", 1)[-1]:
                    deps[-1] = f"{deps[-1]} -> {version}"

        result = [f"lock file ({len(deps)} entries, {total} lines):"]
        for d in deps[:50]:
            result.append(f"  {d}")
        if len(deps) > 50:
            result.append(f"  ... ({len(deps) - 50} more)")
        return "\n".join(result)

    def _compress_poetry_lock(self, lines: list[str], total: int) -> str:
        """poetry.lock: extract [[package]] name and version."""
        deps = []
        current_name = None
        for line in lines:
            stripped = line.strip()
            if stripped == "[[package]]":
                current_name = None
            elif stripped.startswith("name = "):
                val = stripped.split('"')[1] if '"' in stripped else stripped.split("=")[1].strip()
                current_name = val
            elif stripped.startswith("version = ") and current_name:
                val = stripped.split('"')[1] if '"' in stripped else stripped.split("=")[1].strip()
                deps.append(f"{current_name}@{val}")
                current_name = None

        result = [f"poetry.lock ({len(deps)} packages, {total} lines):"]
        for d in deps[:50]:
            result.append(f"  {d}")
        if len(deps) > 50:
            result.append(f"  ... ({len(deps) - 50} more)")
        return "\n".join(result)

    def _compress_cargo_lock(self, lines: list[str], total: int) -> str:
        """Cargo.lock: extract [[package]] name and version."""
        deps = []
        current_name = None
        for line in lines:
            stripped = line.strip()
            if stripped == "[[package]]":
                current_name = None
            elif stripped.startswith("name = "):
                val = stripped.split('"')[1] if '"' in stripped else stripped.split("=")[1].strip()
                current_name = val
            elif stripped.startswith("version = ") and current_name:
                val = stripped.split('"')[1] if '"' in stripped else stripped.split("=")[1].strip()
                deps.append(f"{current_name}@{val}")
                current_name = None

        result = [f"Cargo.lock ({len(deps)} packages, {total} lines):"]
        for d in deps[:50]:
            result.append(f"  {d}")
        if len(deps) > 50:
            result.append(f"  ... ({len(deps) - 50} more)")
        return "\n".join(result)

    def _compress_json_lock(self, raw: str, total: int) -> str:
        """composer.lock / Pipfile.lock: extract package names + versions from JSON."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._truncate_default(raw.splitlines())

        deps = []
        # composer.lock: packages array
        for pkg in data.get("packages", []):
            if isinstance(pkg, dict):
                name = pkg.get("name", "?")
                version = pkg.get("version", "?")
                deps.append(f"{name}@{version}")
        # Pipfile.lock: default + develop dicts
        for section in ("default", "develop"):
            for name, info in data.get(section, {}).items():
                version = info.get("version", "?") if isinstance(info, dict) else "?"
                deps.append(f"{name}{version}")

        result = [f"lock file ({len(deps)} packages, {total} lines):"]
        for d in deps[:50]:
            result.append(f"  {d}")
        if len(deps) > 50:
            result.append(f"  ... ({len(deps) - 50} more)")
        return "\n".join(result)

    def _compress_go_sum(self, lines: list[str], total: int) -> str:
        """go.sum: extract module@version pairs (dedup h1: hashes)."""
        modules = set()
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2:
                modules.add(f"{parts[0]}@{parts[1].split('/')[0]}")

        sorted_mods = sorted(modules)
        result = [f"go.sum ({len(sorted_mods)} modules, {total} lines):"]
        for m in sorted_mods[:50]:
            result.append(f"  {m}")
        if len(sorted_mods) > 50:
            result.append(f"  ... ({len(sorted_mods) - 50} more)")
        return "\n".join(result)

    # ── Structured data compression ──────────────────────────────────

    def _compress_structured(self, lines: list[str], fmt: str) -> str:
        total = len(lines)
        raw = "\n".join(lines)

        if fmt == "json":
            return self._compress_json(raw, total)
        if fmt == "yaml":
            return self._compress_yaml(lines, total)
        if fmt == "toml":
            return self._compress_toml(lines, total)
        if fmt == "xml":
            return self._compress_xml(lines, total)

        return self._truncate_default(lines)

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

    def _compress_toml(self, lines: list[str], total: int) -> str:
        """Keep section headers [section] and key = value lines."""
        result = []
        nested_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Section headers: [section] or [[array]]
            if stripped.startswith("["):
                result.append(line)
            # Key-value at top level (no leading whitespace)
            elif "=" in stripped and not line.startswith((" ", "\t")):
                if len(stripped) > 120:
                    key_part = stripped.split("=", 1)[0].strip()
                    result.append(f"{key_part} = ... (truncated)")
                else:
                    result.append(line)
            else:
                nested_count += 1

        if nested_count > 0:
            result.append(f"  ... ({nested_count} additional lines omitted)")
        result.append(f"\n({total} total lines)")
        return "\n".join(result)

    def _compress_xml(self, lines: list[str], total: int) -> str:
        result = []
        nested_count = 0
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent <= 4 or stripped.startswith(("<?", "<!")):
                result.append(line)
            else:
                nested_count += 1

        if nested_count > 0:
            result.append(f"  ... ({nested_count} nested lines omitted)")
        result.append(f"\n({total} total lines)")
        return "\n".join(result)

    # ── Log compression ─────────────────────────────────────────────

    def _compress_log(self, lines: list[str]) -> str:
        total = len(lines)
        context_lines = config.get("file_log_context_lines")

        head = lines[:5]
        tail = lines[-5:]

        middle = lines[5:-5] if len(lines) > 10 else []
        error_indices = set()
        info_count = 0
        debug_count = 0

        for idx, line in enumerate(middle):
            if _LOG_ERROR_RE.search(line):
                for c in range(idx - context_lines, idx + context_lines + 1):
                    if 0 <= c < len(middle):
                        error_indices.add(c)
            elif re.search(r"\bDEBUG\b", line, re.IGNORECASE):
                debug_count += 1
            elif re.search(r"\bINFO\b", line, re.IGNORECASE):
                info_count += 1

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

        header = lines[0] if lines else ""
        sep = "\t" if "\t" in header else ","
        col_count = header.count(sep) + 1

        result = [lines[0]]
        data_lines = lines[1:]

        if len(data_lines) <= head_rows + tail_rows:
            return "\n".join(lines)

        result.extend(data_lines[:head_rows])
        omitted = len(data_lines) - head_rows - tail_rows
        result.append(f"... ({omitted} rows omitted)")
        result.extend(data_lines[-tail_rows:])
        result.append(f"\n({total - 1} data rows, {col_count} columns)")
        return "\n".join(result)

    # ── Fallback: head/tail truncation ───────────────────────────────

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


def _output_start(lines: list[str]) -> str:
    """Return the first non-whitespace character of the output."""
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped[0]
    return ""
