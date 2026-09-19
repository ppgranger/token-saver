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

"""End-to-end smoke test for install.py against a sandboxed HOME.

The installer is the project's primary distribution path and the only code
with real Windows-specific branches, yet it was previously exercised only
through mocks — nothing ever ran it for real, on any OS.  This drives it
end-to-end in a temporary home directory and then *uses* what it installed,
which is the part mocks cannot check: that the copied tree is complete enough
to import and compress.

Runs on every OS in the CI matrix, which is the point.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = sys.platform == "win32"


def _sandbox_env(home: str) -> dict[str, str]:
    """An environment whose every home-ish path points inside ``home``."""
    env = dict(os.environ)
    # A temporary HOME alone cannot override explicit storage/plugin paths.
    # Also remove import paths so missing installed modules cannot be supplied
    # accidentally by the checkout or a developer's plugin configuration.
    for name in tuple(env):
        if name.startswith(("TOKEN_SAVER_", "PYTEST_", "RUFF_")):
            env.pop(name)
    env.pop("PYTHONPATH", None)
    env["HOME"] = home
    env["USERPROFILE"] = home  # Windows: what expanduser("~") reads
    env["APPDATA"] = os.path.join(home, "AppData", "Roaming")
    env["LOCALAPPDATA"] = os.path.join(home, "AppData", "Local")
    env["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
    env["XDG_DATA_HOME"] = os.path.join(home, ".local", "share")
    env["XDG_CACHE_HOME"] = os.path.join(home, ".cache")
    return env


def _run_installer(home: str, *args: str) -> subprocess.CompletedProcess:
    # Fixed argv, no shell, args are test literals.
    return subprocess.run(  # noqa: S603
        [sys.executable, os.path.join(REPO_ROOT, "install.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_sandbox_env(home),
        cwd=REPO_ROOT,
        timeout=180,
        check=False,
    )


def _data_dir(home: str) -> str:
    if IS_WINDOWS:
        return os.path.join(home, "AppData", "Roaming", "token-saver")
    return os.path.join(home, ".token-saver")


def _claude_dir(home: str) -> str:
    """Claude Code's settings directory inside the sandbox home.

    Mirrors ``installers.claude._settings_dir()``: the roaming profile on
    Windows, a dotfile on POSIX.  Hardcoding ``.claude`` here made this test
    look for a file the installer had correctly written elsewhere.
    """
    if IS_WINDOWS:
        return os.path.join(home, "AppData", "Roaming", "claude")
    return os.path.join(home, ".claude")


@pytest.fixture
def home(tmp_path):
    d = tmp_path / "home"
    d.mkdir()
    return str(d)


def test_install_claude_populates_a_usable_tree(home):
    result = _run_installer(home, "--target", "claude")
    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Installation complete" in result.stdout

    core = _data_dir(home)
    # The engine and the processor package must both be present: a previous
    # release shipped an install missing src/core.py, which broke wrap.py at
    # import time and was invisible to the mocked tests.
    for rel in (
        "src/engine.py",
        "src/core.py",
        "src/command_policy.py",
        "src/telemetry.py",
        "src/updater.py",
        "src/stats_formatting.py",
        "src/config.py",
        "src/delta.py",
        "src/delta_cli.py",
        "src/delta_store.py",
        "src/delta_redaction.py",
        "src/diagnostics.py",
        "src/processors/__init__.py",
    ):
        assert os.path.isfile(os.path.join(core, rel)), (
            f"missing {rel} in {core}"
        )

    # More processors than just the fallback made it across.
    processors = os.listdir(os.path.join(core, "src", "processors"))
    assert len([p for p in processors if p.endswith(".py")]) > 20


def test_installed_tree_actually_compresses(home):
    """Import the *installed* copy and compress with it, not the repo copy."""
    assert _run_installer(home, "--target", "claude").returncode == 0
    core = _data_dir(home)

    program = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from src.engine import CompressionEngine;"
        "out = chr(10).join('file%d.py | 2 ++' % i for i in range(60));"
        "c, p, w = CompressionEngine().compress('git diff --stat', out);"
        "print(p, w, len(c) < len(out))"
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", program, core],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_sandbox_env(home),
        cwd=home,  # deliberately not the repo, so a stray import would fail
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.stdout.split() == ["git", "True", "True"]


def test_sandbox_rejects_inherited_storage_plugins_and_import_paths(
    home, monkeypatch
):
    for name in (
        "TOKEN_SAVER_DB_DIR",
        "TOKEN_SAVER_USER_PROCESSORS_DIR",
        "TOKEN_SAVER_DELTA_ENABLED",
        "PYTHONPATH",
    ):
        monkeypatch.setenv(name, "outside-test-profile")
    environment = _sandbox_env(home)
    assert "PYTHONPATH" not in environment
    assert not any(name.startswith("TOKEN_SAVER_") for name in environment)


def test_installed_delta_repeats_and_reads_without_rerunning(home):
    """Exercise the copied wrapper, store and CLI away from the checkout."""
    assert _run_installer(home, "--target", "claude").returncode == 0
    core = pathlib.Path(_data_dir(home))
    project = pathlib.Path(home) / "fixture project"
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / ".token-saver.json").write_text("{}\n", encoding="utf-8")
    (project / "test_fixture.py").write_text(
        "import pathlib\n"
        "counter = pathlib.Path('executions.txt')\n"
        "prior = counter.read_text(encoding='utf-8')"
        " if counter.exists() else ''\n"
        "counter.write_text(prior + 'x', encoding='utf-8')\n"
        "def test_installed():\n"
        "    actual = list(range(40))\n"
        "    actual[-1] = -1\n"
        "    assert actual == list(range(40)), 'installed failure'\n",
        encoding="utf-8",
    )
    environment = _sandbox_env(home)
    environment.update(
        TOKEN_SAVER_SESSION="installed-smoke",  # noqa: S106 — fixture ID.
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    executable = (
        sys.executable.replace("\\", "/") if IS_WINDOWS else sys.executable
    )
    command = shlex.join(
        [executable, "-m", "pytest", "-vv", "--color=no", "test_fixture.py"]
    )
    arguments = [sys.executable, str(core / "scripts" / "wrap.py"), command]
    results = []
    for enabled in (False, True, True):
        if enabled:
            # S106: feature configuration, not a credential.
            environment.update(TOKEN_SAVER_DELTA_ENABLED="true")  # noqa: S106
        result = subprocess.run(  # noqa: S603 — temporary fixture only.
            arguments,
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
        if not enabled:
            assert not (core / "delta").exists()
            assert "delta show" not in result.stdout
    assert "UNCHANGED test_fixture.py::test_installed" in results[2]
    match = re.search(r"delta show ([0-9a-f]{32})", results[2])
    assert match is not None
    show = subprocess.run(  # noqa: S603 — read the installed local snapshot.
        [
            sys.executable,
            str(core / "bin" / "token-saver"),
            "delta",
            "show",
            match[1],
            "--diagnostic",
            "test_fixture.py::test_installed",
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
    assert "installed failure" in show.stdout
    assert "actual == list(range(40))" in show.stdout
    assert (project / "executions.txt").read_text(encoding="utf-8") == "xxx"


def test_install_registers_the_hook(home):
    assert _run_installer(home, "--target", "claude").returncode == 0
    settings = os.path.join(_claude_dir(home), "settings.json")
    plugins = os.path.join(
        _claude_dir(home), "plugins", "installed_plugins.json"
    )
    assert os.path.isfile(settings) or os.path.isfile(plugins), (
        "installer registered neither settings.json nor installed_plugins.json"
    )
    if os.path.isfile(plugins):
        with open(plugins, encoding="utf-8") as f:
            assert "token-saver" in json.dumps(json.load(f))


def test_uninstall_removes_what_install_created(home):
    assert _run_installer(home, "--target", "claude").returncode == 0
    core = os.path.join(_data_dir(home), "src", "engine.py")
    assert os.path.isfile(core)

    result = _run_installer(home, "--uninstall")
    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert not os.path.exists(core), "uninstall left src/engine.py behind"


def test_install_is_idempotent(home):
    first = _run_installer(home, "--target", "claude")
    second = _run_installer(home, "--target", "claude")
    assert first.returncode == 0
    assert second.returncode == 0, (
        f"re-install failed:\n{second.stdout}\n{second.stderr}"
    )
    assert os.path.isfile(os.path.join(_data_dir(home), "src", "engine.py"))
