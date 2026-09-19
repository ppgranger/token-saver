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

"""Exercise conservative snapshots with complete, partial, and changed runs."""

import argparse
import dataclasses
import os
import subprocess
import sys

import pytest

from src import delta
from src import delta_cli
from src import delta_store
from src import diagnostics
from src.processors import generic
from src.processors import lint_output
from src.processors import test_output

PYTEST_FAILURE = """================ test session starts ================
platform linux -- Python 3.12.0, pytest-8.0.0
rootdir: /work
collected 2 items

tests/test_api.py::test_login PASSED                       [ 50%]
tests/test_api.py::test_invoice FAILED                     [100%]

====================== FAILURES ======================
___________________ test_invoice ____________________

    def test_invoice():
>       assert response.status_code == 200
E       assert 500 == 200
E        + where 500 = response.status_code

tests/test_api.py:18: AssertionError
---------------- Captured stdout call ----------------
request id: 123
================== warnings summary ==================
tests/test_api.py::test_login
  /work/client.py:9: DeprecationWarning: use new_client
    old_client()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============== short test summary info ===============
FAILED tests/test_api.py::test_invoice - assert 500 == 200
=========== 1 failed, 1 passed, 1 warning in 0.12s ===========
plugin teardown: extra information
"""

RUFF_FULL = """warning: configuration migration recommended
F401 [*] `os` imported but unused
 --> app.py:1:8
  |
1 | import os
  |        ^^
  |
help: Remove unused import: `os`

F821 Undefined name `client`
 --> app.py:8:1
  |
8 | client.run()
  | ^^^^^^
  |

Found 2 errors.
[*] 1 fixable with the `--fix` option.
"""

RUFF_CONCISE = """app.py:1:8: F401 [*] `os` imported but unused
app.py:8:1: F821 Undefined name `client`
Found 2 errors.
[*] 1 fixable with the `--fix` option.
"""


def test_snapshot_is_immutable_and_default_extension_declines():
    item = diagnostics.Diagnostic("id", "summary", "details")
    snapshot = diagnostics.Snapshot("test", "1 failed", (item,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.summary = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.detail = "changed"
    assert generic.GenericProcessor().diagnostics("echo test", "test") is None


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests -v",
        "py.test tests -v",
        ".venv/bin/pytest tests -v",
        "'/path with spaces/pytest' tests -v",
        "python3 -m pytest tests -v",
        "/usr/bin/python3.12 -m pytest tests -v",
        "uv run pytest tests -v",
        "poetry run python -m pytest tests -v",
        "pipx run pytest tests -v",
    ],
)
def test_pytest_keeps_full_failure_and_warning_context(command):
    snapshot = test_output.TestOutputProcessor().diagnostics(
        command, PYTEST_FAILURE, exit_code=1
    )
    assert snapshot is not None
    assert snapshot.family == "pytest"
    assert snapshot.summary == "1 failed, 1 passed, 1 warning in 0.12s"
    assert snapshot.passed == ("tests/test_api.py::test_login",)
    assert len(snapshot.diagnostics) == 1
    problem = snapshot.diagnostics[0]
    assert problem.identifier == "tests/test_api.py::test_invoice"
    assert problem.summary == "assert 500 == 200"
    assert "E       assert 500 == 200\n" in problem.detail
    assert "tests/test_api.py:18: AssertionError\n" in problem.detail
    assert "request id: 123\n" in problem.detail
    assert "test session starts" not in snapshot.context
    assert "platform linux" not in snapshot.context
    assert "collected 2 items" not in snapshot.context
    assert " PASSED " not in snapshot.context
    assert " FAILED " not in snapshot.context
    assert "DeprecationWarning: use new_client\n" in snapshot.context
    assert snapshot.context.endswith("plugin teardown: extra information\n")


def test_pytest_changed_assertion_changes_exact_detail():
    processor = test_output.TestOutputProcessor()
    previous = processor.diagnostics("pytest -v", PYTEST_FAILURE)
    current = processor.diagnostics(
        "pytest -v", PYTEST_FAILURE.replace("500", "503")
    )
    assert previous is not None
    assert current is not None
    assert (
        previous.diagnostics[0].identifier == current.diagnostics[0].identifier
    )
    assert previous.diagnostics[0].detail != current.diagnostics[0].detail
    assert "assert 503 == 200" in current.diagnostics[0].detail


def test_pytest_passing_totals_do_not_prove_missing_test_passed():
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -q", ". [100%]\n1 passed in 0.02s\n", exit_code=0
    )
    assert snapshot is not None
    assert snapshot.diagnostics == ()
    assert snapshot.passed == ()


def test_pytest_explicit_verbose_pass_can_confirm_previous_failure():
    output = """================ test session starts ================
collected 1 item

tests/test_api.py::test_invoice PASSED                     [100%]

================ 1 passed in 0.02s ====================
"""
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output
    )
    assert snapshot is not None
    assert snapshot.passed == ("tests/test_api.py::test_invoice",)


def test_pytest_collecting_prefix_and_plugin_header_preserve_pass_proof():
    output = PYTEST_FAILURE.replace(
        "collected 2 items",
        "asyncio: mode=Mode.STRICT\ncollecting ... collected 2 items",
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output
    )
    assert snapshot is not None
    assert snapshot.passed == ("tests/test_api.py::test_login",)
    assert "asyncio: mode=Mode.STRICT\n" in snapshot.context


@pytest.mark.parametrize(
    "output",
    [
        PYTEST_FAILURE.partition("=========== 1 failed")[0],
        PYTEST_FAILURE.replace("1 failed,", "2 failed,"),
        PYTEST_FAILURE.replace("test_invoice _", "unknown _"),
        PYTEST_FAILURE.replace("FAILURES", "ERRORS"),
        PYTEST_FAILURE.replace("FAILED tests/test_api.py", "FAILED other.py"),
        PYTEST_FAILURE + "!!!!!!!! KeyboardInterrupt !!!!!!!!\n",
        PYTEST_FAILURE + "[output truncated]\n",
        PYTEST_FAILURE + "1 passed in 0.03s\n",
        PYTEST_FAILURE.replace("1 failed, 1 passed,", "1 failed, 1 failed,"),
        PYTEST_FAILURE.replace("short test summary info", "unknown section"),
    ],
)
def test_pytest_partial_or_ambiguous_results_decline(output):
    assert (
        test_output.TestOutputProcessor().diagnostics("pytest", output) is None
    )


def test_pytest_duplicate_failure_names_decline():
    block = """______________ test_same ______________
E       assert False
tests/test_first.py:1: AssertionError
"""
    output = (
        "================ FAILURES ================\n"
        + block
        + block.replace("test_first.py", "test_second.py")
        + "========= short test summary info =========\n"
        + "FAILED tests/test_first.py::test_same - assert False\n"
        + "FAILED tests/test_second.py::test_same - assert False\n"
        + "2 failed in 0.02s\n"
    )
    assert (
        test_output.TestOutputProcessor().diagnostics("pytest", output) is None
    )


def test_pytest_repeated_node_with_failed_and_passed_outcomes_declines(
    tmp_path,
):
    # Pytest allows a file to be selected twice. A stateful test may then fail
    # on its first call and pass on the second under the same node identity.
    source = """calls = 0

def test_repeat():
    global calls
    calls += 1
    assert calls > 1
"""
    (tmp_path / "test_repeat.py").write_text(source, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    arguments = [
        sys.executable,
        "-m",
        "pytest",
        "--color=no",
        "-v",
        "--keep-duplicates",
        "-c",
        "pytest.ini",
        "test_repeat.py",
        "test_repeat.py",
    ]
    # The executable and arguments are fixed; only harmless fixture code runs.
    captured = subprocess.run(  # noqa: S603
        arguments,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert captured.returncode == 1, captured.stdout + captured.stderr
    assert "test_repeat.py::test_repeat FAILED" in captured.stdout
    assert "test_repeat.py::test_repeat PASSED" in captured.stdout
    assert (
        test_output.TestOutputProcessor().diagnostics(
            "pytest --color=no -v --keep-duplicates -c pytest.ini "
            "test_repeat.py test_repeat.py",
            captured.stdout,
            exit_code=captured.returncode,
        )
        is None
    )


def test_pytest_parameterized_class_identity_is_stable():
    output = PYTEST_FAILURE.replace(
        "test_invoice", "TestAPI.test_invoice[missing token]"
    ).replace("::TestAPI.", "::TestAPI::")
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output
    )
    assert snapshot is not None
    assert snapshot.diagnostics[0].identifier == (
        "tests/test_api.py::TestAPI::test_invoice[missing token]"
    )


@pytest.mark.parametrize(
    "parameter",
    [
        "timeout - read",
        "literal[inside] - close",
        "paths::and.dots - value",
        "ends] - AssertionError: fake",
    ],
)
def test_pytest_parameter_separators_preserve_diagnostic_identity(parameter):
    title = f"TestAPI.test_invoice[{parameter}]"
    output = PYTEST_FAILURE.replace("test_invoice", title).replace(
        "::TestAPI.", "::TestAPI::"
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output, exit_code=1
    )
    assert snapshot is not None
    assert snapshot.diagnostics[0].identifier == (
        f"tests/test_api.py::TestAPI::test_invoice[{parameter}]"
    )
    assert snapshot.diagnostics[0].summary == "assert 500 == 200"


def test_pytest_real_nested_traceback_and_parameterized_failures(tmp_path):
    source = """import pytest

@pytest.mark.parametrize("value", [1], ids=["a - b"])
def test_parameter(value):
    assert value == 2

def helper():
    raise RuntimeError("nested failure details")

class TestAPI:
    def test_helper(self):
        helper()

def test_diff():
    assert list(range(8)) == list(reversed(range(8)))

def test_pass():
    pass
"""
    (tmp_path / "test_probe.py").write_text(source, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    arguments = [
        sys.executable,
        "-m",
        "pytest",
        "--color=no",
        "-vv",
        "-c",
        "pytest.ini",
        "test_probe.py",
    ]
    # The executable and arguments are fixed; only harmless fixture code runs.
    captured = subprocess.run(  # noqa: S603
        arguments,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert captured.returncode == 1, captured.stdout + captured.stderr
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest --color=no -vv -c pytest.ini test_probe.py",
        captured.stdout,
        exit_code=captured.returncode,
    )
    assert snapshot is not None, captured.stdout
    assert snapshot.passed == ("test_probe.py::test_pass",)
    assert [item.identifier for item in snapshot.diagnostics] == [
        "test_probe.py::test_parameter[a - b]",
        "test_probe.py::TestAPI::test_helper",
        "test_probe.py::test_diff",
    ]
    assert "assert 1 == 2" in snapshot.diagnostics[0].detail
    assert "helper()" in snapshot.diagnostics[1].detail
    assert (
        "RuntimeError: nested failure details" in snapshot.diagnostics[1].detail
    )
    assert "Full diff:" in snapshot.diagnostics[2].detail
    assert (
        "FAILED test_probe.py::test_diff" not in snapshot.diagnostics[2].detail
    )
    assert "Full diff:" not in snapshot.context


def _pytest_multiline_summary():
    continuation = "  Differing values:\n  - expected\n  + actual\n"
    detail = "".join(
        "E       " + line for line in continuation.splitlines(True)
    )
    output = PYTEST_FAILURE.replace(
        "E        + where 500 = response.status_code\n", detail
    ).replace(
        "FAILED tests/test_api.py::test_invoice - assert 500 == 200\n",
        "FAILED tests/test_api.py::test_invoice - assert 500 == 200\n"
        + continuation,
    )
    return output, continuation


def test_pytest_multiline_summary_omits_only_verified_redundant_copy():
    output, continuation = _pytest_multiline_summary()
    output = output.replace(
        continuation + "===========",
        continuation + "plugin: follow-up notice\n===========",
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -vv", output
    )
    assert snapshot is not None
    for line in continuation.splitlines():
        assert "E       " + line in snapshot.diagnostics[0].detail
    assert continuation not in snapshot.context
    assert "plugin: follow-up notice\n" in snapshot.context
    assert "DeprecationWarning: use new_client\n" in snapshot.context
    repeated = delta.render(snapshot, previous=snapshot, exit_code=1)
    assert continuation not in repeated
    assert "plugin: follow-up notice\n" in repeated


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_pytest_summary_dedup_preserves_primary_detail_through_retrieval(
    tmp_path, monkeypatch, capsys, newline
):
    output, continuation = _pytest_multiline_summary()
    output = output.replace(
        continuation + "===========",
        continuation + "plugin: follow-up notice\n===========",
    ).replace("\n", newline)
    primary = output[
        output.index("___________________ test_invoice") : output.index(
            "================== warnings summary"
        )
    ]
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -vv", output, exit_code=1
    )
    assert snapshot is not None
    assert snapshot.diagnostics[0].detail == primary
    initial = delta.render(snapshot, exit_code=1)
    assert primary.rstrip("\r\n") in initial
    assert "plugin: follow-up notice" in initial
    assert "DeprecationWarning: use new_client" in initial
    for line in continuation.splitlines():
        assert initial.count(line) == 1

    directory = str(tmp_path / "snapshots")

    def open_test_store():
        return delta_store.Store(directory)

    payload = dataclasses.asdict(snapshot)
    payload.update(schema=1, exit_code=1)
    with open_test_store() as store:
        run_id = store.save("parser-summary-dedup", payload)
    monkeypatch.setattr(delta, "open_store", open_test_store)
    delta_cli.cmd_show(argparse.Namespace(run_id=run_id, diagnostic=None))
    restored = capsys.readouterr().out
    assert primary.rstrip("\r\n") in restored
    assert "plugin: follow-up notice" in restored
    assert "DeprecationWarning: use new_client" in restored
    delta_cli.cmd_show(
        argparse.Namespace(
            run_id=run_id, diagnostic=snapshot.diagnostics[0].identifier
        )
    )
    assert capsys.readouterr().out == primary


@pytest.mark.parametrize(
    "replacement",
    [
        "  Differing values:\n  - unexpected\n  + actual\n",
        "  Differing values:\n",
    ],
)
def test_pytest_unknown_or_partial_summary_continuation_remains_context(
    replacement,
):
    output, continuation = _pytest_multiline_summary()
    output = output.replace(continuation, replacement)
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -vv", output
    )
    assert snapshot is not None
    assert replacement in snapshot.context


def test_pytest_captured_error_text_cannot_absorb_summary_context():
    output, continuation = _pytest_multiline_summary()
    fake_error = "".join(
        "E       " + line for line in continuation.splitlines(True)
    )
    output = output.replace(fake_error, "", 1).replace(
        "request id: 123\n", "E       assert 500 == 200\n" + fake_error
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -vv", output
    )
    assert snapshot is not None
    assert continuation in snapshot.context


def test_pytest_logged_pass_text_is_not_confirmation():
    output = PYTEST_FAILURE.replace(
        "collected 2 items",
        "collected 2 items\nplugin log: test status follows",
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output
    )
    assert snapshot is not None
    assert snapshot.passed == ()
    assert "plugin log: test status follows\n" in snapshot.context


def test_pytest_unknown_trailing_output_is_always_context():
    output = PYTEST_FAILURE.replace(
        "---------------- Captured stdout call ----------------\n"
        "request id: 123\n",
        "plugin: unusual teardown condition\n",
    )
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest -v", output
    )
    assert snapshot is not None
    assert "plugin: unusual teardown condition\n" in snapshot.context
    assert "unusual teardown" not in snapshot.diagnostics[0].detail


@pytest.mark.parametrize(
    "command",
    [
        "pytest --tb=no",
        "pytest --capture=no",
        "pytest -s",
        "pytest -sv",
        "pytest --collect-only",
        "pytest --no-summary",
        "echo pytest",
        "pytest && ruff check .",
        "pytest | head",
        "pytest; pytest",
        "pytest > output.txt",
        "pytest\npytest",
        "pytest $(echo tests)",
        "pytest 'unterminated",
        "jest",
    ],
)
def test_pytest_unsupported_invocations_decline(command):
    assert (
        test_output.TestOutputProcessor().diagnostics(command, PYTEST_FAILURE)
        is None
    )


@pytest.mark.parametrize("exit_code", [0, 2, 3, 4, 5, 130])
def test_pytest_inconsistent_or_incomplete_exit_status_declines(exit_code):
    assert (
        test_output.TestOutputProcessor().diagnostics(
            "pytest", PYTEST_FAILURE, exit_code=exit_code
        )
        is None
    )


@pytest.mark.parametrize(
    "command",
    [
        "ruff check .",
        "ruff check . --output-format=full",
        "ruff check . --output-format concise",
        ".venv/bin/ruff check .",
        "python -m ruff check .",
        "/usr/bin/python3.12 -m ruff check .",
        "uv run ruff check .",
        "poetry run ruff check .",
    ],
)
@pytest.mark.parametrize("output", [RUFF_FULL, RUFF_CONCISE])
def test_ruff_preserves_diagnostics_and_context(command, output):
    snapshot = lint_output.LintOutputProcessor().diagnostics(
        command, output, exit_code=1
    )
    assert snapshot is not None
    assert snapshot.family == "ruff"
    assert snapshot.summary == "Found 2 errors."
    assert len(snapshot.diagnostics) == 2
    assert snapshot.diagnostics[0].identifier == "app.py:1:8:F401"
    assert (
        snapshot.diagnostics[0].summary == "F401 [*] `os` imported but unused"
    )
    assert "`os` imported but unused" in snapshot.diagnostics[0].detail
    assert snapshot.diagnostics[1].identifier == "app.py:8:1:F821"
    assert "Undefined name `client`" in snapshot.diagnostics[1].detail
    assert "[*] 1 fixable with the `--fix` option.\n" in snapshot.context
    if output == RUFF_FULL:
        assert (
            "warning: configuration migration recommended\n" in snapshot.context
        )
        assert (
            "help: Remove unused import: `os`\n"
            in snapshot.diagnostics[0].detail
        )
        assert "8 | client.run()\n" in snapshot.diagnostics[1].detail


def test_ruff_old_full_format_and_windows_locations():
    output = """C:\\work\\app.py:1:8: F401 [*] `os` imported but unused
  |
1 | import os
  |        ^^
  |
  = help: Remove unused import: `os`
Found 1 error.
"""
    snapshot = lint_output.LintOutputProcessor().diagnostics(
        "ruff check .", output
    )
    assert snapshot is not None
    assert snapshot.diagnostics[0].identifier == r"C:\work\app.py:1:8:F401"
    # Older help syntax is preserved even when it is not part of the block.
    assert "= help: Remove unused import" in snapshot.context


def test_ruff_changed_source_changes_exact_detail():
    processor = lint_output.LintOutputProcessor()
    previous = processor.diagnostics("ruff check .", RUFF_FULL)
    current = processor.diagnostics(
        "ruff check .", RUFF_FULL.replace("client.run()", "client.close()")
    )
    assert previous is not None
    assert current is not None
    assert (
        previous.diagnostics[1].identifier == current.diagnostics[1].identifier
    )
    assert previous.diagnostics[1].detail != current.diagnostics[1].detail


def test_ruff_unknown_interstitial_text_is_always_context():
    output = RUFF_FULL.replace(
        "F821 Undefined", "plugin: something important\nF821 Undefined"
    )
    snapshot = lint_output.LintOutputProcessor().diagnostics(
        "ruff check .", output
    )
    assert snapshot is not None
    assert "plugin: something important\n" in snapshot.context


def test_ruff_clean_run_does_not_invent_passed_identities():
    snapshot = lint_output.LintOutputProcessor().diagnostics(
        "ruff check .", "All checks passed!\n", exit_code=0
    )
    assert snapshot is not None
    assert snapshot.diagnostics == ()
    assert snapshot.passed == ()


@pytest.mark.parametrize(
    "output",
    [
        RUFF_FULL.replace("Found 2 errors.\n", ""),
        RUFF_FULL.replace("Found 2 errors.", "Found 3 errors."),
        RUFF_FULL.replace(" --> app.py:8:1\n", ""),
        RUFF_FULL.replace(
            "Found 2 errors.", "Found 2 errors (1 fixed, 1 remaining)."
        ),
        RUFF_CONCISE.replace("app.py:8:1: F821", "app.py:1:8: F401"),
        RUFF_CONCISE + "Found 2 errors.\n",
        "Found 1 error.\napp.py:1:1: F821 Undefined name `missing`\n",
        "[]\n",
        "<testsuites />\n",
        "error: invalid configuration\n",
    ],
)
def test_ruff_partial_or_ambiguous_results_decline(output):
    assert (
        lint_output.LintOutputProcessor().diagnostics("ruff check .", output)
        is None
    )


@pytest.mark.parametrize(
    "arguments",
    [
        "--fix",
        "--fix-only",
        "--unsafe-fixes",
        "--diff",
        "--statistics",
        "--output-format=json",
        "--output-format junit",
        "--output-format",
        "--show-files",
        "--exit-zero",
        "--watch",
        "--quiet",
        "-q",
        "--output-file=report.txt",
    ],
)
def test_ruff_mutating_or_unsupported_modes_decline(arguments):
    assert (
        lint_output.LintOutputProcessor().diagnostics(
            f"ruff check . {arguments}", RUFF_FULL
        )
        is None
    )


@pytest.mark.parametrize(
    "command", ["ruff format .", "flake8 .", "echo ruff check"]
)
def test_ruff_other_commands_decline(command):
    assert (
        lint_output.LintOutputProcessor().diagnostics(command, RUFF_FULL)
        is None
    )


@pytest.mark.parametrize("exit_code", [0, 2, 130])
def test_ruff_inconsistent_or_incomplete_exit_status_declines(exit_code):
    assert (
        lint_output.LintOutputProcessor().diagnostics(
            "ruff check .", RUFF_FULL, exit_code=exit_code
        )
        is None
    )


def test_ruff_snapshot_size_is_bounded():
    lines = []
    for index in range(diagnostics.MAX_DIAGNOSTICS + 1):
        lines.append(f"app.py:{index + 1}:1: F821 Undefined name `client`\n")
    lines.append(f"Found {len(lines)} errors.\n")
    assert (
        lint_output.LintOutputProcessor().diagnostics(
            "ruff check .", "".join(lines)
        )
        is None
    )


def test_line_endings_in_failure_detail_are_not_normalized():
    snapshot = test_output.TestOutputProcessor().diagnostics(
        "pytest", PYTEST_FAILURE.replace("\n", "\r\n")
    )
    assert snapshot is not None
    assert "E       assert 500 == 200\r\n" in snapshot.diagnostics[0].detail
    assert snapshot.context.endswith("plugin teardown: extra information\r\n")
