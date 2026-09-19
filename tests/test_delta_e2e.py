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

"""Exercise actual pytest runs through the wrapper and installed CLI shape."""

import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

from src import delta_store

_REPO = pathlib.Path(__file__).resolve().parent.parent
_TEST_MODULE = """import json
from pathlib import Path

state = json.loads(Path("state.json").read_text(encoding="utf-8"))
count = Path("executions.txt")
old = count.read_text(encoding="utf-8") if count.exists() else ""
count.write_text(old + "x", encoding="utf-8")

def test_login():
    assert state["login"], "login still broken"

def test_refresh():
    assert state["refresh"], "refresh still broken"

def test_invoice():
    assert state["invoice"], "invoice newly broken"
"""


def test_actual_pytest_repeats_changes_and_detail_retrieval(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    profile = tmp_path / "profile"
    profile.mkdir()
    (project / "test_example.py").write_text(_TEST_MODULE, encoding="utf-8")
    state = project / "state.json"
    state.write_text(
        json.dumps({"login": False, "refresh": False, "invoice": True}),
        encoding="utf-8",
    )
    environment = dict(os.environ)
    # Avoid inheriting real storage, plugins or tuning from the developer.
    for key in list(environment):
        if key.startswith(("TOKEN_SAVER_", "PYTEST_")):
            environment.pop(key)
    environment.update(
        HOME=str(profile),
        USERPROFILE=str(profile),
        APPDATA=str(profile),
        TOKEN_SAVER_DB_DIR=str(tmp_path / "data"),
        TOKEN_SAVER_DELTA_ENABLED="true",  # noqa: S106 — config, not a secret.
        TOKEN_SAVER_SESSION="e2e-session",  # noqa: S106 — synthetic session ID.
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    # The wrapper uses Git Bash on Windows, so its command needs POSIX paths
    # as well as POSIX quoting (single quotes preserve backslashes literally).
    executable = sys.executable.replace("\\", "/")
    if os.name != "nt":
        # Exercise Windows-style routing on every CI platform, including the
        # quoted-space path that ordinary POSIX interpreter locations miss.
        # Invoke the original interpreter explicitly: a relocated symlink can
        # lose its virtual environment and therefore its pytest installation.
        launcher = tmp_path / "Python tools" / "python.exe"
        launcher.parent.mkdir()
        launcher.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o700)
        executable = str(launcher)
    command = shlex.join([executable, "-m", "pytest", "-v", "--color=no"])
    results = []
    for number in range(3):
        if number == 2:
            state.write_text(
                json.dumps({"login": True, "refresh": False, "invoice": False}),
                encoding="utf-8",
            )
        result = subprocess.run(  # noqa: S603 — fixed local fixture commands.
            [sys.executable, str(_REPO / "scripts" / "wrap.py"), command],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert result.returncode == 1, result.stderr
        results.append(result.stdout)
    assert (project / "executions.txt").read_text(encoding="utf-8") == "xxx"
    assert "UNCHANGED test_example.py::test_refresh" in results[1]
    assert len(results[1]) < len(results[0])
    # New failure details must remain visible whether Delta or ordinary output
    # wins the size comparison. Removed failures never become synthetic passes.
    assert "invoice newly broken" in results[2]
    assert "refresh still broken" in results[2]
    assert "PASSED test_example.py::test_refresh" not in results[2]
    match = re.search(r"delta show ([0-9a-f]{32})", results[1])
    assert match is not None
    show = subprocess.run(  # noqa: S603 — read our opaque local snapshot ID.
        [
            sys.executable,
            str(_REPO / "bin" / "token-saver"),
            "delta",
            "show",
            match[1],
            "--diagnostic",
            "test_example.py::test_refresh",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert show.returncode == 0, show.stderr
    assert 'assert state["refresh"]' in show.stdout
    assert "refresh still broken" in show.stdout
    assert (project / "executions.txt").read_text(encoding="utf-8") == "xxx"
    with delta_store.Store(str(tmp_path / "data" / "delta")) as store:
        assert store.clear() == 3
