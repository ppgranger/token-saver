"""Shared utilities for output processors."""

import re
from collections import defaultdict


def compress_json_value(value, depth=0, max_depth=4, important_key_re=None):
    """Recursively compress a JSON value, truncating at depth.

    Args:
        value: The JSON value to compress.
        depth: Current nesting depth.
        max_depth: Maximum depth before summarising.
        important_key_re: Compiled regex — matching dict keys are preserved
            at full depth.  When *None*, no key receives special treatment.
    """
    if depth >= max_depth:
        if isinstance(value, dict):
            return f"{{... {len(value)} keys}}"
        if isinstance(value, list):
            return f"[... {len(value)} items]"
        if isinstance(value, str) and len(value) > 200:
            return value[:197] + "..."
        return value

    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            # Preserve important keys at full depth
            if important_key_re is not None and important_key_re.search(k):
                result[k] = compress_json_value(v, depth, max_depth + 1, important_key_re)
            else:
                result[k] = compress_json_value(v, depth + 1, max_depth, important_key_re)
        return result

    if isinstance(value, list):
        if len(value) == 0:
            return value
        # Don't increment depth for list traversal
        if len(value) <= 5:
            return [compress_json_value(item, depth, max_depth, important_key_re) for item in value]
        compressed = [
            compress_json_value(item, depth, max_depth, important_key_re) for item in value[:3]
        ]
        compressed.append(f"... ({len(value) - 3} more items)")
        return compressed

    if isinstance(value, str) and len(value) > 200:
        return value[:197] + "..."

    return value


def compress_diff(lines, max_hunk, max_context):
    """Compress a unified diff, shared by git.py and gh.py.

    Returns a list of compressed output lines.
    """
    result = []
    hunk_line_count = 0
    hunk_truncated = False
    stat_line = ""
    leading_buffer: list[str] = []
    trailing_remaining = 0

    for line in lines:
        if line.startswith("diff --git"):
            leading_buffer = []
            trailing_remaining = 0
            if hunk_truncated:
                result.append(f"  ... (truncated after {max_hunk} lines)")
            result.append(line)
            hunk_line_count = 0
            hunk_truncated = False
        elif line.startswith(("index ", "---", "+++")):
            continue
        elif line.startswith("@@"):
            leading_buffer = []
            trailing_remaining = 0
            if hunk_truncated:
                result.append(f"  ... (truncated after {max_hunk} lines)")
            result.append(line)
            hunk_line_count = 0
            hunk_truncated = False
        elif line.startswith(("+", "-")):
            hunk_line_count += 1
            if hunk_line_count <= max_hunk:
                if leading_buffer:
                    result.extend(leading_buffer[-max_context:])
                    leading_buffer = []
                result.append(line)
                trailing_remaining = max_context
            elif not hunk_truncated:
                hunk_truncated = True
        elif line.startswith(" "):
            hunk_line_count += 1
            if hunk_line_count <= max_hunk:
                if trailing_remaining > 0:
                    result.append(line)
                    trailing_remaining -= 1
                else:
                    leading_buffer.append(line)
            elif not hunk_truncated:
                hunk_truncated = True
        elif re.match(r"^\s*\d+ files? changed", line):
            stat_line = line

    if hunk_truncated:
        result.append(f"  ... (truncated after {max_hunk} lines)")
    if stat_line:
        result.append(stat_line)

    return result


def group_files_by_dir(lines, max_files):
    """Group a list of file paths by directory.

    Returns a formatted list of strings ready for output.
    """
    by_dir: dict[str, list[str]] = defaultdict(list)
    for raw_path in lines:
        path = raw_path.strip()
        if not path:
            continue
        parts = path.rsplit("/", 1)
        dir_name = parts[0] if len(parts) > 1 else "."
        file_name = parts[-1] if len(parts) > 1 else path
        by_dir[dir_name].append(file_name)

    result = [f"{len(lines)} files found:"]
    dirs = sorted(by_dir.items(), key=lambda x: -len(x[1]))
    for dir_path, files in dirs[:max_files]:
        if len(files) > 10:
            exts: dict[str, int] = defaultdict(int)
            for f in files:
                ext = f.rsplit(".", 1)[-1] if "." in f else "(none)"
                exts[ext] += 1
            ext_desc = ", ".join(
                f"*.{e}:{n}" for e, n in sorted(exts.items(), key=lambda x: -x[1])[:4]
            )
            result.append(f"  {dir_path}/ ({len(files)} files: {ext_desc})")
        elif len(files) > 5:
            result.append(f"  {dir_path}/ ({len(files)} files): {', '.join(files[:3])} ...")
        else:
            for f in files:
                result.append(f"  {dir_path}/{f}")

    if len(dirs) > max_files:
        result.append(f"... ({len(dirs) - max_files} more directories)")

    return result
