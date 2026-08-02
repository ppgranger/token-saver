"""Keep ``hook_patterns`` and ``can_handle`` from drifting apart.

Every processor states which commands it wants twice: ``hook_patterns`` decides
whether the PreToolUse hook *intercepts* a command, and ``can_handle`` decides
whether the engine *routes* to it.  Nothing structurally ties the two together,
so they can silently disagree — and when they do, the failure is invisible:
either the hook pays the wrapping cost for a command no processor will handle,
or a processor advertises commands the hook never sends it.

The duplication is a design wart worth removing one day.  Until then, these
tests make the disagreement loud.  They currently pass with zero violations
across a corpus harvested from the whole test suite; the point is to notice the
first regression, not to fix a present-day bug.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors import discover_processors
from tests.failure_fixtures import CASES

PROCESSORS = discover_processors()
FIXTURE_COMMAND = {c.processor: c.command for c in CASES}


def _corpus() -> list[str]:
    """Command strings harvested from the test suite itself.

    Using the suite as the corpus means the guard automatically widens as
    contributors add cases, instead of relying on a list nobody maintains.
    """
    found: set[str] = set()
    pattern = re.compile(r'(?:is_compressible|can_handle|compress)\(\s*(["\'])(.+?)\1')
    for path in pathlib.Path(__file__).parent.glob("*.py"):
        for match in pattern.finditer(path.read_text()):
            command = match.group(2)
            if command and len(command) < 120 and "\\n" not in command:
                found.add(command)
    found.update(FIXTURE_COMMAND.values())
    return sorted(found)


CORPUS = _corpus()


def test_corpus_is_substantial():
    """A corpus that quietly shrank to nothing would make every test below pass."""
    assert len(CORPUS) > 300, f"only {len(CORPUS)} commands harvested"


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.name)
def test_hook_patterns_imply_can_handle(processor):
    """If the hook intercepts a command for this processor, it must accept it.

    A violation means the hook wraps commands — paying a subprocess and an
    interpreter start — that this processor then refuses.
    """
    compiled = [re.compile(p) for p in processor.hook_patterns]
    disagreements = [
        command
        for command in CORPUS
        if any(p.search(command) for p in compiled) and not processor.can_handle(command)
    ]
    assert disagreements == [], (
        f"{processor.name}: hook_patterns match these but can_handle rejects them: "
        f"{disagreements[:5]}"
    )


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.name)
def test_hook_patterns_are_anchored(processor):
    """Patterns decide interception on the whole command; unanchored ones
    match mid-string and would wrap unrelated commands (``cat notes-git.txt``).
    """
    unanchored = [p for p in processor.hook_patterns if not p.startswith("^")]
    assert unanchored == [], f"{processor.name} has unanchored hook_patterns: {unanchored}"


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.name)
def test_hook_patterns_compile(processor):
    for pattern in processor.hook_patterns:
        re.compile(pattern)  # raises re.error on a malformed pattern


@pytest.mark.parametrize("processor", PROCESSORS, ids=lambda p: p.name)
def test_failure_fixture_command_would_be_intercepted(processor):
    """The command each processor is tested with must be one the hook wraps.

    Otherwise the processor is only reachable through chaining, and its
    fixture proves nothing about the real path.
    """
    if not processor.hook_patterns:
        pytest.skip(f"{processor.name} is the fallback and has no hook_patterns")
    command = FIXTURE_COMMAND[processor.name]
    assert any(re.search(p, command) for p in processor.hook_patterns), (
        f"{processor.name}: fixture command {command!r} is not matched by its own "
        "hook_patterns, so the hook would never route it here"
    )
