#!/usr/bin/env python3
"""Verify that every committed version string agrees with ``src/__init__.py``.

``installers/common.py:stamp_version()`` rewrites the manifests at *install*
time, so a drifted manifest never breaks an install — which is exactly why the
drift goes unnoticed.  What it does break is ``/plugin update``: Claude Code
keys its update cache on the ``version`` in ``.claude-plugin/plugin.json``, so a
release whose bump missed that file ships to nobody.  This check makes the
release commit fail in CI instead.

    python3 scripts/check_versions.py

Exits 0 when everything matches, 1 with a per-file report otherwise.
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, ROOT)

from installers.common import _read_version  # noqa: E402

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

# Manifests carrying a top-level "version" key.
JSON_MANIFESTS = (
    ".claude-plugin/plugin.json",
    "antigravity/antigravity-plugin.json",
)

# marketplace.json nests the version inside plugins[].version; plugin.json wins
# at resolution time, but a stale entry here still misleads anyone reading the
# catalog.
MARKETPLACE = ".claude-plugin/marketplace.json"

# Prose that quotes the version, and the pattern that pins it.
PROSE_FILES = (
    ("docs/benchmarks.md", re.compile(r"^Version: \*\*(?P<version>[^*]+)\*\*", re.MULTILINE)),
)

CHANGELOG = "CHANGELOG.md"


def _read(rel_path: str) -> str:
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _collect(expected: str) -> list[str]:
    """Return one error line per file that disagrees with ``expected``."""
    errors = []

    for rel_path in JSON_MANIFESTS:
        found = json.loads(_read(rel_path)).get("version")
        if found != expected:
            errors.append(f"{rel_path}: version is {found!r}, expected {expected!r}")

    for entry in json.loads(_read(MARKETPLACE)).get("plugins", []):
        found = entry.get("version")
        if found != expected:
            name = entry.get("name", "?")
            errors.append(
                f"{MARKETPLACE}: plugins[{name}].version is {found!r}, expected {expected!r}",
            )

    for rel_path, pattern in PROSE_FILES:
        match = pattern.search(_read(rel_path))
        if match is None:
            errors.append(f"{rel_path}: no version line matching {pattern.pattern!r}")
        elif match.group("version") != expected:
            found = match.group("version")
            errors.append(f"{rel_path}: version is {found!r}, expected {expected!r}")

    # The plugin pins an explicit version, so users only receive a release once
    # it is written down.  A missing entry means the release is undocumented.
    if not os.path.exists(os.path.join(ROOT, CHANGELOG)):
        errors.append(f"{CHANGELOG}: missing")
    elif f"## [{expected}]" not in _read(CHANGELOG):
        errors.append(f"{CHANGELOG}: no '## [{expected}]' section for the current version")

    return errors


def main() -> int:
    expected = _read_version()

    if not SEMVER.match(expected):
        print(f"FAIL src/__init__.py: __version__ {expected!r} is not semver MAJOR.MINOR.PATCH")
        return 1

    errors = _collect(expected)
    if errors:
        print(f"FAIL version drift (src/__init__.py declares {expected}):")
        for error in errors:
            print(f"  - {error}")
        print("\nsrc/__init__.py is the source of truth; update the files above to match.")
        return 1

    print(f"OK all version strings agree on {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
