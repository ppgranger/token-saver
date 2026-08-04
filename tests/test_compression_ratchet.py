"""Compression ratios are the product; this stops them regressing silently.

The README advertises specific numbers ("npm install 3,844 -> 4 tokens, 99%").
Until now nothing verified them: ``scripts/audit_compression.py`` measured real
ratios but was never run by CI, and the only ratio assertion in the suite was
guarded by ``if was_compressed:`` — so a regression that stopped compressing
altogether made the test pass.

This locks each scenario to a recorded baseline.  When a change legitimately
alters a ratio, regenerate:

    python3 -c "import sys,json,pathlib; sys.path.insert(0,'.'); \\
        from scripts.audit_compression import measure; \\
        pathlib.Path('tests/compression_baselines.json').write_text(json.dumps( \\
            {r.label: {'processor': r.processor, 'was_compressed': r.was_compressed, \\
                       'ratio': round(r.ratio,1)} for r in measure()}, \\
            indent=2, sort_keys=True) + chr(10), encoding='utf-8')"

and justify the change in the PR.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.audit_compression import SCENARIOS, measure

#: Ratios are deterministic, so this only absorbs incidental drift from
#: refactors — not a real loss of compression.
TOLERANCE_PP = 2.0

BASELINES = json.loads(
    (pathlib.Path(__file__).parent / "compression_baselines.json").read_text(encoding="utf-8")
)

RESULTS = {r.label: r for r in measure()}


def test_baselines_and_scenarios_are_in_sync():
    """Adding a scenario must come with a baseline, and vice versa."""
    assert {s.label for s in SCENARIOS} == set(BASELINES), (
        "scenarios and tests/compression_baselines.json have diverged — "
        "regenerate the baselines (see this module's docstring)"
    )


@pytest.mark.parametrize("label", sorted(BASELINES), ids=lambda s: s[:40])
def test_ratio_does_not_regress(label):
    expected = BASELINES[label]
    actual = RESULTS[label]
    assert actual.ratio >= expected["ratio"] - TOLERANCE_PP, (
        f"{label}: compression dropped from {expected['ratio']}% to {actual.ratio:.1f}%"
    )


@pytest.mark.parametrize("label", sorted(BASELINES), ids=lambda s: s[:40])
def test_still_compresses(label):
    """Unconditional, unlike the old `if was_compressed:` assertion."""
    expected = BASELINES[label]
    actual = RESULTS[label]
    assert actual.was_compressed == expected["was_compressed"], (
        f"{label}: was_compressed went from {expected['was_compressed']} to {actual.was_compressed}"
    )


@pytest.mark.parametrize("label", sorted(BASELINES), ids=lambda s: s[:40])
def test_routes_to_the_same_processor(label):
    """A silent routing change is a regression even when the ratio holds."""
    expected = BASELINES[label]
    actual = RESULTS[label]
    assert actual.processor == expected["processor"], (
        f"{label}: now routed to {actual.processor!r}, was {expected['processor']!r}"
    )


def test_overall_ratio_holds():
    """Aggregate guard, so many small losses can't slip under the tolerance."""
    total_orig = sum(r.original_tokens for r in RESULTS.values())
    total_comp = sum(r.compressed_tokens for r in RESULTS.values())
    overall = (total_orig - total_comp) / total_orig * 100
    baseline_overall = 68.0
    assert overall >= baseline_overall, (
        f"overall compression fell to {overall:.1f}% (floor {baseline_overall}%)"
    )
