"""One version, declared once, asserted everywhere.

``src/__init__.py`` is the source of truth — ``installers/common.py``
``_read_version()`` reads it and stamps the plugin manifests from it at install
time.  But three other files carried the version too, and nothing kept them
honest: ``pyproject.toml`` was maintained entirely by hand, and
``antigravity/antigravity-plugin.json`` had already drifted to ``1.0.0`` while
the rest said ``2.6.3``.

``pyproject.toml`` no longer declares a version at all (it derives one via
``[tool.setuptools.dynamic]``), so it cannot drift.  The JSON manifests still
have to carry a literal, because they are read as data by the Claude Code
marketplace before anything is installed — a stale value there is visible to
users browsing the plugin.  These tests are what keep them correct.

Releasing is therefore: bump ``src/__init__.py``, run this test, fix what it
names.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import __version__

REPO_ROOT = pathlib.Path(__file__).parent.parent


def _load(rel: str) -> dict:
    return json.loads((REPO_ROOT / rel).read_text())


@pytest.mark.parametrize(
    "rel",
    [".claude-plugin/plugin.json", "antigravity/antigravity-plugin.json"],
)
def test_manifest_version_matches_source(rel):
    assert _load(rel)["version"] == __version__, (
        f"{rel} is out of sync with src/__init__.py ({__version__})"
    )


def test_marketplace_catalog_version_matches_source():
    """marketplace.json keeps its version nested under plugins[]."""
    for entry in _load(".claude-plugin/marketplace.json")["plugins"]:
        if "version" in entry:
            assert entry["version"] == __version__, (
                f".claude-plugin/marketplace.json plugin {entry.get('name')!r} is out of sync "
                f"with src/__init__.py ({__version__})"
            )


def test_pyproject_declares_no_literal_version():
    """A hand-maintained duplicate is what caused the drift; keep it derived."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    project_table = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    assert not re.search(r'^\s*version\s*=\s*["\']', project_table, re.M), (
        "pyproject.toml declares a literal version again — it should stay "
        'dynamic = ["version"] reading src.__version__'
    )
    assert 'dynamic = ["version"]' in project_table


def test_version_looks_like_a_release():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), (
        f"__version__ = {__version__!r} is not a plain semver triple"
    )
