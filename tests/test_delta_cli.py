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

"""Public retrieval behavior with real private, temporary snapshot storage."""

import argparse
import sqlite3

import pytest

from src import delta
from src import delta_cli
from src import delta_store


@pytest.fixture
def saved_snapshot(tmp_path, monkeypatch):
    directory = str(tmp_path / "delta")
    monkeypatch.setattr(
        delta, "open_store", lambda: delta_store.Store(directory)
    )
    payload = {
        "schema": 1,
        "exit_code": 1,
        "family": "pytest",
        "summary": "2 failed",
        "context": "a retained warning\n",
        "passed": [],
        "diagnostics": [
            {
                "identifier": "tests/test_a.py::test_a",
                "summary": "first assertion",
                "detail": "first assertion details\n",
            },
            {
                "identifier": "tests/test_b.py::test_b[case with spaces]",
                "summary": "second assertion",
                "detail": "second assertion details\n",
            },
        ],
    }
    with delta.open_store() as store:
        return store.save("scope", payload)


def _run(*arguments):
    parser = argparse.ArgumentParser(prog="token-saver")
    delta_cli.add_delta_parsers(parser.add_subparsers(required=True))
    args = parser.parse_args(["delta", *arguments])
    args.handler(args)


def test_targeted_retrieval_accepts_exact_parameterized_test_id(
    saved_snapshot, capsys
):
    _run(
        "show",
        saved_snapshot,
        "--diagnostic",
        "tests/test_b.py::test_b[case with spaces]",
    )
    captured = capsys.readouterr()
    assert captured.out == "second assertion details\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "identifier", ["tests/test_b.py::test_b", "first assertion", "", "*"]
)
def test_targeted_retrieval_never_uses_partial_or_pattern_matches(
    saved_snapshot, capsys, identifier
):
    with pytest.raises(SystemExit) as failure:
        _run("show", saved_snapshot, "--diagnostic", identifier)
    assert failure.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Diagnostic not in this snapshot.\n"


def test_retrieval_masks_recognized_secrets_in_legacy_stored_content(
    saved_snapshot, tmp_path, capsys
):
    database = tmp_path / "delta" / "snapshots.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE snapshots SET payload = replace(payload, ?, ?)",
            ("first assertion details", "API_TOKEN=synthetic-private-value"),
        )
    _run("show", saved_snapshot, "--diagnostic", "tests/test_a.py::test_a")
    captured = capsys.readouterr()
    assert "synthetic-private-value" not in captured.out + captured.err
    assert captured.out == "API_TOKEN=***\n"


def test_corrupt_database_errors_never_disclose_content(
    saved_snapshot, tmp_path, capsys
):
    database = tmp_path / "delta" / "snapshots.sqlite3"
    database.write_bytes(b"synthetic-private-database-content")
    for arguments in (("show", saved_snapshot), ("clear",)):
        with pytest.raises(SystemExit) as failure:
            _run(*arguments)
        assert failure.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "synthetic-private" not in captured.err
        assert "Traceback" not in captured.err
        assert "safely" in captured.err


def test_deeply_nested_record_is_rejected_without_a_traceback(
    saved_snapshot, tmp_path, capsys
):
    # Python 3.10-3.12 can reject this during decoding; newer decoders can
    # reach schema validation. Both paths must produce the same safe error.
    nested = '{"private":' + "[" * 10000 + "0" + "]" * 10000 + "}"
    database = tmp_path / "delta" / "snapshots.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE snapshots SET payload = ?", (nested,))
    with pytest.raises(SystemExit) as failure:
        _run("show", saved_snapshot)
    assert failure.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Cannot read Delta snapshot safely.\n"


def test_clear_invalidates_saved_ids_and_all_comparison_scopes(
    saved_snapshot, capsys
):
    with delta.open_store() as store:
        store.save("other-session-and-command", {"summary": "other result"})
    _run("clear")
    assert capsys.readouterr().out == "Cleared 2 Delta snapshot(s).\n"
    with pytest.raises(SystemExit) as failure:
        _run("show", saved_snapshot)
    assert failure.value.code == 1
    with delta.open_store() as store:
        assert store.latest("scope") is None
        assert store.latest("other-session-and-command") is None
