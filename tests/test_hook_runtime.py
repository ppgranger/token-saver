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

"""Interpreter compatibility at hook and wrapper entry points."""

import io
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest

from scripts import hook_pretool
from scripts import wrap

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Keep hook subprocess configuration and recording in a temporary home."""
    for name in tuple(os.environ):
        if name.startswith("TOKEN_SAVER_"):
            monkeypatch.delenv(name)
    for name in ("HOME", "USERPROFILE", "APPDATA"):
        monkeypatch.setenv(name, str(tmp_path))
    return os.environ.copy()


@pytest.mark.parametrize(
    ("entrypoint", "exit_code"),
    [
        ("scripts/hook_pretool.py", 0),
        ("scripts/hook_session.py", 0),
        ("src/hook_session.py", 0),
        ("antigravity/hook_aftertool.py", 0),
        ("scripts/wrap.py", 1),
    ],
)
def test_old_python_reports_requirement_before_runtime_imports(
    entrypoint, exit_code, isolated_env, tmp_path
):
    # Simulate the version in a fresh process so cached project imports cannot
    # hide a runtime import before the guard. The guard must precede them all.
    runner = (
        "import runpy, sys; sys.version_info = (3, 9, 6); "
        "runpy.run_path(sys.argv[1], run_name='__main__')"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", runner, str(_REPO_ROOT / entrypoint)],
        input="{}",
        capture_output=True,
        encoding="utf-8",
        timeout=10,
        check=False,
        cwd=tmp_path,
        env=isolated_env,
    )
    assert result.returncode == exit_code
    assert result.stdout == ""
    assert "Python 3.10+ is required" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / ".token-saver").exists()


@pytest.mark.parametrize(
    "executable",
    [
        "/opt/Python builds/it's python;$(echo injected)/python3.11",
        r"C:\Program Files\Python311\python.exe",
    ],
)
def test_rewrite_quotes_the_running_interpreter(
    executable, monkeypatch, capsys, isolated_env
):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "session_id": "session with spaces",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "executable", executable)
    with pytest.raises(SystemExit) as error:
        hook_pretool.main()
    assert error.value.code == 0
    response = json.loads(capsys.readouterr().out)
    command = response["hookSpecificOutput"]["updatedInput"]["command"]
    assert shlex.split(command) == [
        "TOKEN_SAVER_SESSION=session with spaces",
        executable,
        str(_REPO_ROOT / "scripts" / "wrap.py"),
        "git status",
    ]


def test_rewritten_command_ignores_other_python_on_path(tmp_path, isolated_env):
    """A supported hook must not hand its command to a different interpreter."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("python", "python3"):
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        # These inert shell fixtures must be executable to expose PATH lookup.
        executable.chmod(0o755)
    isolated_env["PATH"] = (
        str(fake_bin) + os.pathsep + isolated_env.get("PATH", "")
    )
    (tmp_path / "fixture.txt").write_text("original output\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(_REPO_ROOT / "scripts" / "hook_pretool.py")],
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "cat fixture.txt"}}
        ),
        capture_output=True,
        encoding="utf-8",
        timeout=10,
        check=False,
        cwd=tmp_path,
        env=isolated_env,
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    command = response["hookSpecificOutput"]["updatedInput"]["command"]
    shell = wrap.posix_shell() or shutil.which("bash")
    assert shell is not None, "The supported host requires a POSIX shell"
    executed = subprocess.run(  # noqa: S603
        [shell, "-c", command],
        capture_output=True,
        encoding="utf-8",
        timeout=10,
        check=False,
        cwd=tmp_path,
        env=isolated_env,
    )
    assert executed.returncode == 0, executed.stderr
    assert executed.stdout == "original output\n"
