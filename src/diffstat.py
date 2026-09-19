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

"""Structured diff summary between original and compressed output.

Used by ``token-saver benchmark`` and wrap.py ``--dry-run`` to show *what*
compression removed, not just the headline ratio.  Works purely from the
before/after strings (no per-processor instrumentation), so it stays accurate
for every processor without coupling to their internals.
"""

from __future__ import annotations

import difflib


def summarize(original: str, compressed: str) -> dict:
    """Describe removed and added lines without retaining complete outputs.

    Args:
        original: Original captured output before compression.
        compressed: Output after compression.

    Returns:
        A mapping of line counts, added/removed line counts, net character
        reduction, and up to five nonempty samples of added and removed lines.
    """
    orig_lines = original.splitlines()
    comp_lines = compressed.splitlines()

    removed: list[str] = []
    added: list[str] = []
    matcher = difflib.SequenceMatcher(
        None, orig_lines, comp_lines, autojunk=False
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(orig_lines[i1:i2])
        if tag in ("insert", "replace"):
            added.extend(comp_lines[j1:j2])

    return {
        "original_lines": len(orig_lines),
        "compressed_lines": len(comp_lines),
        "lines_removed": len(removed),
        "lines_added": len(added),
        "chars_removed": len(original) - len(compressed),
        "removed_samples": [s for s in removed if s.strip()][:5],
        "added_samples": [s for s in added if s.strip()][:5],
    }


def format_summary(summary: dict) -> str:
    """Render :func:`summarize` output as an indented text block.

    Args:
        summary: Metrics and line samples produced by summarize().

    Returns:
        A multiline report suitable for terminal display.
    """
    lines = [
        "Removed breakdown:",
        f"  Lines:  {summary['original_lines']:,} -> "
        f"{summary['compressed_lines']:,} "
        f"({summary['lines_removed']:,} removed, "
        f"{summary['lines_added']:,} added)",
        f"  Chars:  {summary['chars_removed']:,} removed",
    ]
    if summary["removed_samples"]:
        lines.append("  Sample removed lines:")
        for s in summary["removed_samples"]:
            lines.append(f"    - {s[:100]}")
    if summary["added_samples"]:
        lines.append("  Sample added (summary) lines:")
        for s in summary["added_samples"]:
            lines.append(f"    + {s[:100]}")
    return "\n".join(lines)
