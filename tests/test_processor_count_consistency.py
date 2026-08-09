"""One processor count, discovered once, asserted everywhere.

``src/processors/discover_processors()`` is the source of truth. But the
processor count is also *hand-typed* into five other places for marketing/doc
purposes — README, docs/comparison.md, the config skill, and the two plugin
manifests — and nothing kept them honest: plugin.json and marketplace.json
drifted to "32" while everything else said "36" and the registry actually
returns 36. A stale count in a plugin manifest is visible to users browsing
the Claude Code marketplace, and public docs sites (and the LLMs that cite
them) will happily propagate whichever number they scrape first.

Adding, removing, or splitting a processor is therefore: run this test, fix
whatever it names.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors import discover_processors

REPO_ROOT = pathlib.Path(__file__).parent.parent


def _processor_count() -> int:
    return len(discover_processors())


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _json(rel: str) -> dict:
    return json.loads(_text(rel))


@pytest.mark.parametrize(
    ("rel", "pattern"),
    [
        ("README.md", r"\*\*(\d+) specialized processors\*\*"),
        ("docs/comparison.md", r"\| \*\*Compression method\*\* \| (\d+) specialized processors"),
        ("skills/token-saver-config/SKILL.md", r"(\d+) specialized processors, auto-discovered"),
    ],
)
def test_doc_processor_count_matches_registry(rel, pattern):
    match = re.search(pattern, _text(rel))
    assert match, f"{rel} does not contain the expected processor-count phrase"
    assert int(match.group(1)) == _processor_count(), (
        f"{rel} says {match.group(1)} processors but "
        f"discover_processors() returns {_processor_count()}"
    )


def test_plugin_manifest_processor_count_matches_registry():
    description = _json(".claude-plugin/plugin.json")["description"]
    match = re.search(r"(\d+) specialized processors", description)
    assert match, ".claude-plugin/plugin.json description has no processor count"
    assert int(match.group(1)) == _processor_count(), (
        f".claude-plugin/plugin.json says {match.group(1)} processors but "
        f"discover_processors() returns {_processor_count()}"
    )


def test_marketplace_catalog_processor_count_matches_registry():
    for entry in _json(".claude-plugin/marketplace.json")["plugins"]:
        match = re.search(r"(\d+) specialized processors", entry["description"])
        if not match:
            continue
        assert int(match.group(1)) == _processor_count(), (
            f".claude-plugin/marketplace.json plugin {entry.get('name')!r} says "
            f"{match.group(1)} processors but discover_processors() returns "
            f"{_processor_count()}"
        )
