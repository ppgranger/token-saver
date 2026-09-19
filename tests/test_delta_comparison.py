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

"""Shared diagnostic evidence policy, independent of storage and rendering."""

import dataclasses

import pytest

from src import delta
from src import diagnostics


def _problem(identifier, summary="assert 1 == 2", detail="full traceback"):
    return diagnostics.Diagnostic(identifier, summary, detail)


def test_comparison_preserves_observation_order_and_explicit_pass_evidence():
    absent = _problem("absent")
    changed = _problem("changed")
    passed = _problem("passed")
    unchanged = _problem("unchanged")
    added = _problem("added")
    modified = dataclasses.replace(changed, detail="new traceback")
    previous = diagnostics.Snapshot(
        "pytest", "4 failed", (absent, changed, passed, unchanged)
    )
    current = diagnostics.Snapshot(
        "pytest",
        "3 failed, 1 passed",
        (added, modified, unchanged),
        ("passed",),
    )

    changes = diagnostics.compare(current, previous)

    assert tuple(change.diagnostic for change in changes) == (
        added,
        modified,
        unchanged,
        absent,
        passed,
    )
    assert tuple(change.status for change in changes) == (
        "NEW",
        "CHANGED",
        "UNCHANGED",
        "NOT OBSERVED",
        "PASSED",
    )
    assert tuple(change.needs_detail for change in changes) == (
        True,
        True,
        False,
        False,
        False,
    )
    assert delta.render(current, exit_code=1, previous=previous) == (
        "[token-saver delta] pytest | exit 1\n"
        "3 failed, 1 passed\n"
        "NEW added — assert 1 == 2\nfull traceback\n"
        "CHANGED changed — assert 1 == 2\nnew traceback\n"
        "UNCHANGED unchanged — assert 1 == 2\n"
        "NOT OBSERVED absent — not confirmed fixed\n"
        "PASSED passed — explicitly passed this run\n"
    )


@pytest.mark.parametrize("baseline_family", [None, "ruff"])
def test_missing_or_incompatible_baseline_cannot_hide_current_details(
    baseline_family,
):
    problem = _problem("test_a")
    current = diagnostics.Snapshot("pytest", "1 failed", (problem,))
    previous = None
    if baseline_family is not None:
        previous = diagnostics.Snapshot(baseline_family, "1 error", (problem,))

    changes = diagnostics.compare(current, previous)

    assert len(changes) == 1
    assert changes[0].status == "NEW"
    assert changes[0].needs_detail


@pytest.mark.parametrize(
    "replacement",
    [
        {"identifier": "renamed"},
        {"summary": "new problem explanation"},
        {"detail": "new traceback evidence"},
    ],
)
def test_identity_summary_or_detail_changes_always_require_current_evidence(
    replacement,
):
    original = _problem("test_a")
    updated = dataclasses.replace(original, **replacement)
    previous = diagnostics.Snapshot("pytest", "1 failed", (original,))
    current = diagnostics.Snapshot("pytest", "1 failed", (updated,))

    changes = diagnostics.compare(current, previous)

    assert changes[0].diagnostic == updated
    assert changes[0].needs_detail
    assert updated.detail in delta.render(
        current, exit_code=1, previous=previous
    )


def test_run_context_changes_remain_visible_without_invalidating_diagnostics():
    problem = _problem("test_a")
    previous = diagnostics.Snapshot("pytest", "1 failed", (problem,))
    current = diagnostics.Snapshot(
        "pytest", "1 failed, 5 passed", (problem,), context="new warning\n"
    )

    changes = diagnostics.compare(current, previous)
    rendered = delta.render(current, exit_code=1, previous=previous)

    assert changes[0].status == "UNCHANGED"
    assert not changes[0].needs_detail
    assert current.summary in rendered
    assert current.context in rendered
    assert problem.detail not in rendered
