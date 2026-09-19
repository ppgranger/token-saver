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

"""Session-delta behavior and conservative integration boundaries."""

import dataclasses
import json
import pathlib
import re
import sys
from unittest import mock

import pytest

from scripts import wrap
from src import cli
from src import config
from src import core
from src import delta
from src import delta_store
from src import diagnostics
from src import engine
from src.processors import base
from src.processors import generic


@pytest.fixture(autouse=True)
def isolated_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TOKEN_SAVER_DELTA_ENABLED", "true")
    monkeypatch.setenv("TOKEN_SAVER_ENABLED", "true")
    monkeypatch.setenv("TOKEN_SAVER_SESSION", "test-session")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config.reload()
    yield
    config.reload()


def _snapshot(*items, passed=(), context=""):
    return diagnostics.Snapshot(
        family="pytest",
        summary=f"{len(items)} failed, 5 passed",
        diagnostics=tuple(items),
        passed=passed,
        context=context,
    )


def _diagnostic(identifier="tests/test_a.py::test_a", message="assert 1 == 2"):
    detail = "\n".join([f"context line {i}" for i in range(20)])
    return diagnostics.Diagnostic(identifier, message, detail + "\n" + message)


def _apply(snapshot, *, output="captured output", session="test-session"):
    compressor = engine.CompressionEngine()
    ordinary = "ordinary output " * 200
    baseline = core.CompressResult(
        ordinary, "test", True, False, "test", 4000, len(ordinary)
    )
    with mock.patch.object(compressor, "diagnostics", return_value=snapshot):
        return delta.apply(
            "pytest -v",
            output,
            baseline,
            engine=compressor,
            exit_code=1,
            session_id=session,
        )


def _run_id(result):
    match = re.search(r"delta show ([0-9a-f]{32})", result.compressed)
    assert match is not None
    return match.group(1)


def test_lifecycle_keeps_current_failures_and_only_confirms_explicit_passes():
    first = _diagnostic()
    second = _diagnostic("tests/test_b.py::test_b")
    third = _diagnostic("tests/test_c.py::test_c")
    previous = _snapshot(first, second, third)
    changed = _diagnostic(first.identifier, "assert 3 == 4")
    new = _diagnostic("tests/test_new.py::test_new")
    current = _snapshot(changed, new, passed=(second.identifier,))
    text = delta.render(current, previous=previous, exit_code=1)
    assert f"CHANGED {first.identifier}" in text
    assert changed.detail in text
    assert f"NEW {new.identifier}" in text
    assert f"PASSED {second.identifier}" in text
    assert f"NOT OBSERVED {third.identifier}" in text
    assert "not confirmed fixed" in text
    assert "exit 1" in text
    assert "2 failed, 5 passed" in text


def test_identical_details_elided_but_current_inventory_and_context_remain():
    item = _diagnostic()
    current = _snapshot(item, context="UserWarning: investigate this warning")
    first = _apply(current)
    repeated = _apply(current)
    assert item.detail in first.compressed
    assert item.detail not in repeated.compressed
    assert f"UNCHANGED {item.identifier}" in repeated.compressed
    assert item.summary in repeated.compressed
    assert current.context in repeated.compressed
    assert repeated.compressed_len < first.compressed_len
    with delta.open_store() as store:
        retained = store.get(_run_id(repeated))
    restored, status = delta.restore(retained)
    assert restored == current
    assert status == 1


def test_changed_detail_never_hidden_even_if_summary_is_identical():
    first = _diagnostic()
    _apply(_snapshot(first))
    changed = dataclasses.replace(
        first, detail=first.detail + "\nextra evidence"
    )
    result = _apply(_snapshot(changed))
    assert "CHANGED" in result.compressed
    assert changed.detail in result.compressed


def test_size_gate_avoids_repeat_overhead_without_truncating_fresh_details():
    snapshot = _snapshot(_diagnostic())
    compressor = engine.CompressionEngine()
    baseline = core.CompressResult(
        "ordinary short output", "test", True, False, "test", 2000, 21
    )
    with mock.patch.object(compressor, "diagnostics", return_value=snapshot):
        first = delta.apply(
            "pytest",
            "raw",
            baseline,
            engine=compressor,
            exit_code=1,
            session_id="gate",
        )
        repeated = delta.apply(
            "pytest",
            "raw",
            baseline,
            engine=compressor,
            exit_code=1,
            session_id="gate",
        )
    assert snapshot.diagnostics[0].detail in first.compressed
    assert first.compressed_len > baseline.compressed_len
    assert repeated is baseline


def test_recognized_secrets_never_reach_delta_storage(tmp_path):
    output = (
        "F821 Undefined name `unknown`\n"
        " --> example.py:1:1\n"
        "  |\n"
        '1 | API_KEY = "synthetic-secret-value"\n'
        "  | ^^^^^^^\n\n"
        "Found 1 error.\n"
    )
    compressor = engine.CompressionEngine()
    baseline = core.compress(
        "ruff check .", output, engine=compressor, exit_code=1
    )
    result = delta.apply(
        "ruff check .",
        output,
        baseline,
        engine=compressor,
        exit_code=1,
        session_id="redaction",
    )
    assert "synthetic-secret-value" not in result.compressed
    database = tmp_path / "data" / "delta" / "snapshots.sqlite3"
    assert database.exists()
    assert b"synthetic-secret-value" not in database.read_bytes()
    with delta.open_store() as store:
        prior = store.latest(delta._scope("ruff check .", "redaction", "ruff"))
    assert prior is not None
    assert "synthetic-secret-value" not in json.dumps(prior[1])


def test_session_and_working_directory_separate_baselines(
    tmp_path, monkeypatch
):
    snapshot = _snapshot(_diagnostic())
    _apply(snapshot)
    assert "NEW" in _apply(snapshot, session="different").compressed
    directory = tmp_path / "different"
    directory.mkdir()
    monkeypatch.chdir(directory)
    assert "NEW" in _apply(snapshot).compressed


def test_disabled_or_missing_session_never_opens_store(monkeypatch):
    snapshot = _snapshot(_diagnostic())
    with mock.patch.object(delta, "open_store") as open_store:
        assert "ordinary output" in _apply(snapshot, session="").compressed
        monkeypatch.setenv("TOKEN_SAVER_DELTA_ENABLED", "false")
        config.reload()
        assert "ordinary output" in _apply(snapshot).compressed
        open_store.assert_not_called()


@pytest.mark.parametrize(
    ("command", "status"),
    [
        ("pytest | tail -20", 0),
        ("pytest && ruff check .", 1),
        ("pytest 2>&1", 1),
        ("pytest", 124),
        ("pytest", 2),
    ],
)
def test_unsafe_scopes_and_incomplete_execution_never_store(command, status):
    baseline = core.CompressResult("old", "test", True, False, "test", 10, 3)
    with mock.patch.object(delta, "open_store") as open_store:
        result = delta.apply(
            command,
            "some output",
            baseline,
            engine=engine.CompressionEngine(),
            exit_code=status,
            session_id="test",
        )
        assert result is baseline
        open_store.assert_not_called()


def test_store_failure_retains_redaction_and_does_not_emit_false_reference():
    output = "API_KEY=synthetic-secret\nAssertionError: important failure\n"
    with mock.patch.object(delta, "open_store", side_effect=OSError):
        result = _apply(_snapshot(_diagnostic()), output=output)
    assert "synthetic-secret" not in result.compressed
    assert "important failure" in result.compressed
    assert "delta show" not in result.compressed
    assert result.original_len == len(output)


def test_parser_failure_is_content_free_and_preserves_command_result(caplog):
    output = "AssertionError: original evidence"
    compressor = engine.CompressionEngine()
    result = core.compress("pytest", output, engine=compressor, exit_code=1)
    with mock.patch.object(
        compressor, "diagnostics", side_effect=RuntimeError("private detail")
    ):
        actual = delta.apply(
            "pytest",
            output,
            result,
            engine=compressor,
            exit_code=1,
            session_id="test",
        )
    assert actual.compressed == result.compressed
    assert "private detail" not in caplog.text
    assert output not in caplog.text
    assert "Delta unavailable" in caplog.text


def test_cli_show_is_complete_and_clear_resets_baseline(monkeypatch, capsys):
    item = _diagnostic()
    result = _apply(_snapshot(item))
    run_id = _run_id(result)
    monkeypatch.setattr(sys, "argv", ["token-saver", "delta", "show", run_id])
    cli.main()
    assert item.detail in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["token-saver", "delta", "clear"])
    cli.main()
    assert "Cleared 1" in capsys.readouterr().out
    assert "NEW" in _apply(_snapshot(item)).compressed


def test_cli_rejects_invalid_and_missing_snapshots(monkeypatch, capsys):
    for run_id, expected in (("../secret", 2), ("a" * 32, 1)):
        monkeypatch.setattr(
            sys, "argv", ["token-saver", "delta", "show", run_id]
        )
        with pytest.raises(SystemExit) as failure:
            cli.main()
        assert failure.value.code == expected
        assert "../secret" not in capsys.readouterr().err


def test_project_cannot_enable_or_extend_retention(tmp_path, monkeypatch):
    monkeypatch.delenv("TOKEN_SAVER_DELTA_ENABLED")
    (tmp_path / ".token-saver.json").write_text(
        json.dumps(
            {
                "delta_enabled": True,
                "delta_retention_hours": 168,
                "delta_max_runs": 1000,
            }
        ),
        encoding="utf-8",
    )
    config.reload()
    assert config.get("delta_enabled") is False
    assert config.get("delta_retention_hours") == 24
    assert config.get("delta_max_runs") == 100


@pytest.mark.parametrize("value", ["0", "-1", "9999"])
def test_invalid_retention_settings_fall_back_to_bounded_defaults(
    monkeypatch, value
):
    monkeypatch.setenv("TOKEN_SAVER_DELTA_RETENTION_HOURS", value)
    monkeypatch.setenv("TOKEN_SAVER_DELTA_MAX_RUNS", value)
    config.reload()
    assert config.get("delta_retention_hours") == 24
    assert config.get("delta_max_runs") == 100


def test_wrapper_executes_once_preserves_exit_and_dry_run_does_not_store(
    monkeypatch, capsys
):
    output = (
        "tests/test_a.py:1:1: F401 `os` imported but unused\nFound 1 error.\n"
    )
    monkeypatch.setattr(sys, "argv", ["wrap.py", "ruff check ."])
    with (
        mock.patch.object(
            wrap, "_run_command", return_value=(output, "", 1)
        ) as execute,
        mock.patch.object(core, "record_saving"),
        pytest.raises(SystemExit) as failure,
    ):
        wrap.main()
    assert execute.call_count == 1
    assert failure.value.code == 1
    assert "F401" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["wrap.py", "--dry-run", "ruff check ."])
    with (
        mock.patch.object(wrap, "_run_command", return_value=(output, "", 1)),
        mock.patch.object(delta, "apply") as apply_delta,
        pytest.raises(SystemExit),
    ):
        wrap.main()
    apply_delta.assert_not_called()


def test_unsupported_parser_never_creates_database():
    compressor = engine.CompressionEngine()
    output = "unrecognized pytest output"
    baseline = core.compress("pytest", output, engine=compressor, exit_code=1)
    result = delta.apply(
        "pytest",
        output,
        baseline,
        engine=compressor,
        exit_code=1,
        session_id="test",
    )
    assert result == baseline
    assert not list(pathlib.Path.cwd().rglob("snapshots.sqlite3"))


def test_disabled_processor_cannot_capture_diagnostics(monkeypatch):
    monkeypatch.setenv("TOKEN_SAVER_DISABLED_PROCESSORS", "lint")
    config.reload()
    compressor = engine.CompressionEngine()
    output = "a.py:1:1: F401 unused import\nFound 1 error.\n"
    assert compressor.diagnostics("ruff check .", output, exit_code=1) is None


def test_corrupt_snapshot_schema_fails_closed():
    with pytest.raises(ValueError, match="snapshot schema"):
        delta.restore({"schema": 999})
    with delta_store.Store() as store:
        run_id = store.save("scope", {"schema": 999})
        assert store.get(run_id) == {"schema": 999}


def test_cli_corrupt_record_does_not_print_a_traceback(monkeypatch, capsys):
    payload = dataclasses.asdict(_snapshot(_diagnostic()))
    payload.update(schema=1, exit_code=1)
    payload["diagnostics"][0]["unexpected"] = "private data"
    with delta.open_store() as store:
        run_id = store.save("bad-shape", payload)
    monkeypatch.setattr(sys, "argv", ["token-saver", "delta", "show", run_id])
    with pytest.raises(SystemExit) as failure:
        cli.main()
    assert failure.value.code == 2
    captured = capsys.readouterr()
    assert "private data" not in captured.out + captured.err
    assert "Traceback" not in captured.err


class _PrivateDiagnosticProcessor(base.Processor):
    """Model an extension whose private masking rule Delta cannot infer."""

    priority = 1
    handles_failure = True

    @property
    def name(self):
        return "private_diagnostics"

    def can_handle(self, command):
        return command == "pytest"

    def process(self, command, output):
        return output.replace("proprietary-value", "[private]")

    def redacted_secrets(self, command, output):
        return "proprietary-value" in output

    def diagnostics(self, command, output, *, exit_code=None):
        return _snapshot(_diagnostic(message=output))


def test_delta_never_restores_a_processors_private_redactions():
    compressor = engine.CompressionEngine(
        [_PrivateDiagnosticProcessor(), generic.GenericProcessor()]
    )
    output = "AssertionError: proprietary-value\n" * 30
    ordinary = core.compress("pytest", output, engine=compressor, exit_code=1)
    assert "proprietary-value" not in ordinary.compressed
    with mock.patch.object(
        delta, "open_store", wraps=delta.open_store
    ) as open_store:
        actual = delta.apply(
            "pytest",
            output,
            ordinary,
            engine=compressor,
            exit_code=1,
            session_id="private-redactions",
        )
    assert "proprietary-value" not in actual.compressed
    assert actual == ordinary
    open_store.assert_not_called()


@pytest.mark.parametrize("schema", [True, 1.0])
def test_snapshot_schema_requires_an_integer_version(schema):
    payload = json.loads(json.dumps(dataclasses.asdict(_snapshot())))
    payload.update(schema=schema, exit_code=0)
    with pytest.raises(ValueError, match="schema"):
        delta.restore(payload)


@pytest.mark.parametrize("passed", [[""], ["test_a", "test_a"]])
def test_stored_passed_inventory_rejects_ambiguous_identities(passed):
    payload = json.loads(json.dumps(dataclasses.asdict(_snapshot())))
    payload.update(schema=1, exit_code=0, passed=passed)
    with pytest.raises(ValueError, match="passed inventory"):
        delta.restore(payload)
