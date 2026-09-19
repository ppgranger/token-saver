# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared utilities for output processors."""

import collections
import re

# Shared Rust compiler output patterns (used by cargo and cargo_clippy
# processors)
RUST_WARNING_START_RE = re.compile(r"^warning(?:\[(\S+)\])?:\s+(.+)")
RUST_ERROR_START_RE = re.compile(r"^error(?:\[(\S+)\])?:\s+(.+)")
RUST_SPAN_LINE_RE = re.compile(r"^\s*(-->|\d+\s*\||=\s+)")
RUST_WARNING_SUMMARY_RE = re.compile(r"^warning:\s+.+generated\s+\d+\s+warning")
RUST_FINISHED_RE = re.compile(r"^\s*Finished\s+")
RUST_COMPILING_RE = re.compile(r"^\s*Compiling\s+\S+\s+v")

_DEFAULT_ERROR_RE = re.compile(
    r"\b(error|Error|ERROR|exception|Exception|EXCEPTION|"
    r"fatal|Fatal|FATAL|panic|Panic|PANIC|traceback|Traceback)\b"
)


def compress_json_value(value, depth=0, max_depth=4, important_key_re=None):
    """Recursively compress a JSON value, truncating at depth.

    Args:
        value: The JSON value to compress.
        depth: Current nesting depth.
        max_depth: Maximum depth before summarising.
        important_key_re: Compiled regex — matching dict keys are preserved
            at full depth.  When *None*, no key receives special treatment.

    Returns:
        A JSON-compatible value with bounded nesting, list samples, and long
        strings replaced by explicit summaries. The input is not mutated.
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
                result[k] = compress_json_value(
                    v, depth, max_depth + 1, important_key_re
                )
            else:
                result[k] = compress_json_value(
                    v, depth + 1, max_depth, important_key_re
                )
        return result

    if isinstance(value, list):
        if len(value) == 0:
            return value
        # Don't increment depth for list traversal
        if len(value) <= 5:
            return [
                compress_json_value(item, depth, max_depth, important_key_re)
                for item in value
            ]
        compressed = [
            compress_json_value(item, depth, max_depth, important_key_re)
            for item in value[:3]
        ]
        compressed.append(f"... ({len(value) - 3} more items)")
        return compressed

    if isinstance(value, str) and len(value) > 200:
        return value[:197] + "..."

    return value


def compress_diff(lines, max_hunk, max_context):
    """Compress a unified diff, shared by git.py and gh.py.

    Args:
        lines: Diff lines without their line endings.
        max_hunk: Maximum number of hunk-body lines inspected before omission.
        max_context: Maximum unchanged lines retained around each change.

    Returns:
        Diff lines with file/hunk headers, changes, bounded context, and
        explicit truncation markers. Binary and rename metadata is preserved.
    """
    result = []
    hunk_line_count = 0
    hunk_truncated = False
    stat_line = ""
    leading_buffer: list[str] = []
    trailing_remaining = 0
    # Track whether we are inside a hunk body.  File-header lines
    # (---/+++/index)
    # only appear *before* the first @@ of a file; once in a hunk, lines
    # starting
    # with +/- are content and must never be treated as headers (a removed line
    # whose text is "-- foo" arrives as "--- foo").
    in_hunk = False

    for line in lines:
        if line.startswith("diff --git"):
            leading_buffer = []
            trailing_remaining = 0
            in_hunk = False
            if hunk_truncated:
                result.append(f"  ... (truncated after {max_hunk} lines)")
            result.append(line)
            hunk_line_count = 0
            hunk_truncated = False
        elif line.startswith("@@"):
            leading_buffer = []
            trailing_remaining = 0
            in_hunk = True
            if hunk_truncated:
                result.append(f"  ... (truncated after {max_hunk} lines)")
            result.append(line)
            hunk_line_count = 0
            hunk_truncated = False
        elif not in_hunk and line.startswith(("index ", "--- ", "+++ ")):
            continue
        elif not in_hunk and line.startswith(
            (
                "Binary files",
                "rename ",
                "copy ",
                "similarity ",
                "dissimilarity ",
                "new file mode",
                "deleted file mode",
                "old mode",
                "new mode",
            )
        ):
            # Preserve metadata for diffs that have no hunk body (binary,
            # pure renames, mode-only changes) — otherwise they'd vanish.
            result.append(line)
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


def group_paths_by_dir(paths: list[str]) -> dict[str, list[str]]:
    """Bucket file paths by their parent directory.

    A path with no separator is filed under ``"."``; one rooted at ``/`` keeps
    its empty parent, so it renders as ``/name`` rather than ``./name``.

    Args:
        paths: Slash-separated paths; blank entries are ignored.

    Returns:
        Directory names mapped to basenames in their original encounter order.
    """
    by_dir: dict[str, list[str]] = collections.defaultdict(list)
    for raw_path in paths:
        path = raw_path.strip()
        if not path:
            continue
        head, sep, tail = path.rpartition("/")
        if sep:
            by_dir[head].append(tail)
        else:
            by_dir["."].append(path)
    return by_dir


def format_dir_group(
    dir_path: str, files: list[str], ext_threshold: int = 10
) -> list[str]:
    """Render one directory bucket, summarising harder as it gets bigger.

    Three tiers: an extension histogram above ``ext_threshold`` files, a
    count plus a sample above five, and the plain list below that.

    This and :func:`group_paths_by_dir` are the parts ``search._process_fd``
    and ``file_listing._process_find`` genuinely share.  They used to be
    copy-pasted into both (and a third time into an unused helper here, whose
    thresholds had drifted from both callers).  What legitimately differs —
    directory ordering, whether to cap the number of directories, and this
    threshold — stays with the callers.

    Args:
        dir_path: Parent directory label used in the rendered lines.
        files: Basenames belonging to that directory, in display order.
        ext_threshold: File count above which to show an extension histogram.

    Returns:
        Indented listing lines or a summary containing counts and a sample.
    """
    if len(files) > ext_threshold:
        exts: dict[str, int] = collections.defaultdict(int)
        for f in files:
            ext = f.rsplit(".", 1)[-1] if "." in f else "(none)"
            exts[ext] += 1
        ext_desc = ", ".join(
            f"*.{e}:{n}"
            for e, n in sorted(exts.items(), key=lambda x: -x[1])[:4]
        )
        return [f"  {dir_path}/ ({len(files)} files: {ext_desc})"]
    if len(files) > 5:
        return [
            f"  {dir_path}/ ({len(files)} files): {', '.join(files[:3])} ..."
        ]
    return [f"  {dir_path}/{f}" for f in files]


def compress_log_lines(
    lines: list[str],
    keep_head: int = 10,
    keep_tail: int = 20,
    error_re: re.Pattern | None = None,
    context_lines: int = 2,
    max_error_lines: int = 50,
) -> str:
    """Keep log boundaries and error lines with their surrounding context.

    Args:
        lines: Log lines without their line endings.
        keep_head: Number of leading lines retained unchanged.
        keep_tail: Number of trailing lines retained unchanged.
        error_re: Pattern identifying error lines; None uses shared defaults.
        context_lines: Number of neighboring lines retained around each error.
        max_error_lines: Maximum middle-section error/context lines to retain.

    Returns:
        Newline-joined text with explicit markers for omitted log sections.
    """
    if len(lines) <= keep_head + keep_tail:
        return "\n".join(lines)

    err_re = error_re or _DEFAULT_ERROR_RE
    head = lines[:keep_head]
    tail = lines[-keep_tail:]
    middle = (
        lines[keep_head:-keep_tail]
        if len(lines) > keep_head + keep_tail
        else []
    )

    # Find error lines with context in the middle section
    error_indices: set[int] = set()
    for idx, line in enumerate(middle):
        if err_re.search(line):
            for c in range(idx - context_lines, idx + context_lines + 1):
                if 0 <= c < len(middle):
                    error_indices.add(c)

    result = head[:]

    if middle:
        if error_indices:
            result.append(
                f"\n... ({len(lines)} total lines, showing errors) ...\n"
            )
            sorted_indices = sorted(error_indices)
            prev = -2
            for idx in sorted_indices:
                if idx > prev + 1 and prev >= 0:
                    gap = idx - prev - 1
                    result.append(f"  ... ({gap} lines skipped)")
                result.append(middle[idx])
                prev = idx
            # Cap error output
            if len(sorted_indices) > max_error_lines:
                result = result[: keep_head + 1 + max_error_lines]
                result.append(
                    f"  ... ({len(sorted_indices) - max_error_lines} more "
                    f"error lines)"
                )
        else:
            result.append(
                f"\n... ({len(lines) - keep_head - keep_tail} lines "
                f"truncated) ...\n"
            )

    result.extend(tail)
    return "\n".join(result)
