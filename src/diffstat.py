"""Structured diff summary between original and compressed output.

Used by ``token-saver benchmark`` and wrap.py ``--dry-run`` to show *what*
compression removed, not just the headline ratio.  Works purely from the
before/after strings (no per-processor instrumentation), so it stays accurate
for every processor without coupling to their internals.
"""

from __future__ import annotations

import difflib


def summarize(original: str, compressed: str) -> dict:
    """Return a structured line/byte breakdown of a compression.

    Keys:
        original_lines, compressed_lines: line counts
        lines_removed:  lines present in original but not in compressed
        lines_added:    lines present in compressed but not original
                        (e.g. summary lines like "... (12 more)")
        chars_removed:  net characters removed
        removed_samples: up to 5 representative removed lines
        added_samples:   up to 5 representative added lines
    """
    orig_lines = original.splitlines()
    comp_lines = compressed.splitlines()

    removed: list[str] = []
    added: list[str] = []
    matcher = difflib.SequenceMatcher(None, orig_lines, comp_lines, autojunk=False)
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
    """Render :func:`summarize` output as an indented text block."""
    lines = [
        "Removed breakdown:",
        f"  Lines:  {summary['original_lines']:,} -> {summary['compressed_lines']:,} "
        f"({summary['lines_removed']:,} removed, {summary['lines_added']:,} added)",
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
