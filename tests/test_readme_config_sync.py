"""README's "Complete Parameter List" must not drift from src.config._DEFAULTS.

This table has drifted silently before — hand-maintained numbers next to a
dict that changes independently.  These tests parse the actual markdown table
and cross-check every row against the real defaults, so a future change to
``_DEFAULTS`` without a matching README edit fails CI instead of shipping.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import _DEFAULTS, _PROJECT_FORBIDDEN_KEYS

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_README_PATH = os.path.join(_REPO_ROOT, "README.md")

_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")


def _read_readme() -> str:
    with open(_README_PATH, encoding="utf-8") as f:
        return f.read()


def _parse_parameter_table() -> dict[str, tuple[str, str]]:
    """Return {key: (default_cell, description_cell)} for every row under
    "Complete Parameter List"."""
    content = _read_readme()
    marker = "### Complete Parameter List"
    start = content.index(marker)
    # Table runs until the next "## " or "### " heading.
    rest = content[start + len(marker) :]
    end_match = re.search(r"\n#{2,3}\s", rest)
    section = rest[: end_match.start()] if end_match else rest

    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        m = _ROW_RE.match(line.strip())
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3))
    return rows


def _format_expected(value) -> str:
    """Render a _DEFAULTS value the way the table is expected to show it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '""' if value == "" else value
    if isinstance(value, list):
        return "[]" if not value else repr(value)
    return str(value)


def test_every_default_key_is_documented():
    documented = _parse_parameter_table()
    missing = set(_DEFAULTS) - documented.keys()
    assert not missing, (
        f"README's Complete Parameter List is missing: {sorted(missing)} — "
        "add a row (see src/config.py's _DEFAULTS for the real default)"
    )


def test_no_stale_or_typo_rows():
    """A row for a key that no longer exists in _DEFAULTS is either a typo
    or leftover from a removed setting — either way, it's actively wrong."""
    documented = _parse_parameter_table()
    stale = documented.keys() - set(_DEFAULTS)
    assert not stale, (
        f"README documents parameters that don't exist in src.config._DEFAULTS: "
        f"{sorted(stale)} — fix the key name or remove the row"
    )


def test_documented_defaults_match_source():
    """The value shown in the table must be the real default, not a stale
    or aspirational one."""
    documented = _parse_parameter_table()
    mismatches = []
    for key, default_val in _DEFAULTS.items():
        if key not in documented:
            continue  # covered by test_every_default_key_is_documented
        expected = _format_expected(default_val)
        cell, _description = documented[key]
        if expected not in cell:
            mismatches.append(f"{key}: README says {cell!r}, _DEFAULTS has {default_val!r}")
    assert not mismatches, "README default values have drifted:\n" + "\n".join(mismatches)


def test_project_forbidden_keys_are_flagged_in_readme():
    """The three keys that a project-level .token-saver.json cannot set must
    say so in their README row — this is a security property, not trivia."""
    documented = _parse_parameter_table()
    for key in _PROJECT_FORBIDDEN_KEYS:
        assert key in documented, f"{key} is missing from the README table entirely"
        _default_cell, description = documented[key]
        assert "not project config" in description or "global config" in description, (
            f"{key}'s README row doesn't mention the project-config restriction: {description!r}"
        )
