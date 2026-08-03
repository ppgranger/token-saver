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
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = sys.platform == "win32"


def _sandbox_env(home: str) -> dict[str, str]:
    """An environment whose every home-ish path points inside ``home``."""
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home  # Windows: what expanduser("~") reads
    env["APPDATA"] = os.path.join(home, "AppData", "Roaming")
    env["LOCALAPPDATA"] = os.path.join(home, "AppData", "Local")
    # Keep the installer from finding a developer config on the CI runner.
    env.pop("TOKEN_SAVER_DATA_DIR", None)
    env.pop("XDG_DATA_HOME", None)
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


@pytest.fixture
def home(tmp_path):
    d = tmp_path / "home"
    d.mkdir()
    return str(d)


def test_install_claude_populates_a_usable_tree(home):
    result = _run_installer(home, "--target", "claude")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "Installation complete" in result.stdout

    core = _data_dir(home)
    # The engine and the processor package must both be present: a previous
    # release shipped an install missing src/core.py, which broke wrap.py at
    # import time and was invisible to the mocked tests.
    for rel in ("src/engine.py", "src/core.py", "src/config.py", "src/processors/__init__.py"):
        assert os.path.isfile(os.path.join(core, rel)), f"missing {rel} in {core}"

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
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.stdout.split() == ["git", "True", "True"]


def test_install_registers_the_hook(home):
    assert _run_installer(home, "--target", "claude").returncode == 0
    settings = os.path.join(home, ".claude", "settings.json")
    plugins = os.path.join(home, ".claude", "plugins", "installed_plugins.json")
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
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not os.path.exists(core), "uninstall left src/engine.py behind"


def test_install_is_idempotent(home):
    first = _run_installer(home, "--target", "claude")
    second = _run_installer(home, "--target", "claude")
    assert first.returncode == 0
    assert second.returncode == 0, f"re-install failed:\n{second.stdout}\n{second.stderr}"
    assert os.path.isfile(os.path.join(_data_dir(home), "src", "engine.py"))
