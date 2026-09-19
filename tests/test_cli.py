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

"""Tests for the token-saver CLI subcommands."""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src

IS_WINDOWS = os.name == "nt"

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_cli(*args, stdin=None):
    """Run the CLI and return its status, stdout, and stderr."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "src.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_DIR,
        input=stdin,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


class TestVersionCommand:
    def test_prints_version(self):
        rc, stdout, _ = _run_cli("version")
        assert rc == 0
        assert f"token-saver v{src.__version__}" in stdout

    def test_version_format(self):
        rc, stdout, _ = _run_cli("version")
        assert rc == 0
        # Should match pattern: token-saver vX.Y.Z
        line = stdout.strip()
        assert line.startswith("token-saver v")
        version_str = line.split("token-saver v")[1]
        parts = version_str.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()


class TestStatsCommand:
    def test_stats_human_readable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(tmp_path))
        rc, stdout, _ = _run_cli("stats")
        assert rc == 0
        assert "Token-Saver Savings" in stdout

    def test_stats_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(tmp_path))
        rc, stdout, _ = _run_cli("stats", "--json")
        assert rc == 0
        data = json.loads(stdout)
        assert "session" in data
        assert "lifetime" in data

    def test_stats_callback_preserves_host_arguments_during_render(
        self, monkeypatch
    ):
        from src import cli
        from src import stats

        original_argv = ["host-app", "--unrelated-option"]
        monkeypatch.setattr(sys, "argv", original_argv)
        received = []

        def render(arguments):
            assert sys.argv is original_argv
            received.append(arguments)

        monkeypatch.setattr(stats, "main", render)
        cli.cmd_stats(argparse.Namespace(json=True))
        cli.cmd_stats(argparse.Namespace(json=False))
        assert received == [["--json"], []]
        assert original_argv == ["host-app", "--unrelated-option"]


class TestNoCommand:
    def test_no_args_shows_help(self):
        rc, stdout, _ = _run_cli()
        assert rc == 0
        assert "token-saver" in stdout.lower() or "usage" in stdout.lower()


class TestBenchmarkCommand:
    def test_benchmark_dry_run(self):
        rc, stdout, _ = _run_cli("benchmark", "git diff HEAD", "--dry-run")
        assert rc == 0
        assert "Processor:" in stdout
        assert "git" in stdout

    def test_benchmark_dry_run_json(self):
        rc, stdout, _ = _run_cli(
            "benchmark", "git diff HEAD", "--dry-run", "--format", "json"
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data["dry_run"] is True
        assert data["processor"] == "git"
        assert data["command"] == "git diff HEAD"

    def test_benchmark_real_command(self):
        rc, stdout, _ = _run_cli("benchmark", "echo hello")
        assert rc == 0
        assert "Token-Saver Benchmark" in stdout
        assert "Original:" in stdout
        assert "Compressed:" in stdout

    def test_benchmark_json_format(self):
        rc, stdout, _ = _run_cli("benchmark", "echo hello", "--format", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert "original_chars" in data
        assert "compressed_chars" in data
        assert "processor" in data
        assert "savings_percent" in data

    def test_benchmark_show_removed_text(self):
        rc, stdout, _ = _run_cli(
            "benchmark", "git log --oneline -50", "--show-removed"
        )
        assert rc == 0
        assert "Removed breakdown:" in stdout
        assert "Lines:" in stdout

    def test_benchmark_show_removed_json(self):
        rc, stdout, _ = _run_cli(
            "benchmark",
            "git log --oneline -50",
            "--show-removed",
            "--format",
            "json",
        )
        assert rc == 0
        data = json.loads(stdout)
        assert "removed" in data
        assert "lines_removed" in data["removed"]
        assert "chars_removed" in data["removed"]

    def test_benchmark_no_show_removed_omits_key(self):
        rc, stdout, _ = _run_cli("benchmark", "echo hello", "--format", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert "removed" not in data

    def test_benchmark_stdin_compresses_piped_output(self):
        piped = (
            "\n".join(f"{i:07x} commit message {i}" for i in range(50)) + "\n"
        )
        rc, stdout, _ = _run_cli(
            "benchmark",
            "git log --oneline",
            "--stdin",
            "--format",
            "json",
            stdin=piped,
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data["processor"] == "git"
        assert data["original_chars"] == len(piped)
        assert data["compressed_chars"] < data["original_chars"]

    def test_benchmark_stdin_does_not_execute(self):
        # Command would fail if executed, but --stdin must not run it.
        rc, stdout, _ = _run_cli(
            "benchmark",
            "git log --oneline",
            "--stdin",
            "--format",
            "json",
            stdin="hello world\n",
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data["original_chars"] == len("hello world\n")


class TestDiffstat:
    def test_summarize_removed_lines(self):
        import src.diffstat

        original = "a\nb\nc\nd\ne\n"
        compressed = "a\ne\n"
        s = src.diffstat.summarize(original, compressed)
        assert s["original_lines"] == 5
        assert s["compressed_lines"] == 2
        assert s["lines_removed"] == 3
        assert s["chars_removed"] == len(original) - len(compressed)
        assert "b" in s["removed_samples"]

    def test_summarize_added_summary_line(self):
        import src.diffstat

        original = "x\ny\nz\n"
        compressed = "x\n... (2 more)\n"
        s = src.diffstat.summarize(original, compressed)
        assert s["lines_added"] >= 1
        assert any("more" in a for a in s["added_samples"])

    def test_summarize_no_change(self):
        import src.diffstat

        s = src.diffstat.summarize("same\n", "same\n")
        assert s["lines_removed"] == 0
        assert s["lines_added"] == 0
        assert s["chars_removed"] == 0

    def test_format_summary_contains_sections(self):
        import src.diffstat

        text = src.diffstat.format_summary(
            src.diffstat.summarize("a\nb\nc\n", "a\n")
        )
        assert "Removed breakdown:" in text
        assert "Lines:" in text
        assert "Chars:" in text


class TestMarketplaceDetection:
    def test_cache_path_is_marketplace_managed(self):
        import src.cli

        path = os.path.join(
            os.path.expanduser("~"),
            ".claude",
            "plugins",
            "cache",
            "token-saver-marketplace",
            "token-saver",
        )
        assert src.cli._is_marketplace_managed(path) is True

    def test_regular_repo_not_marketplace_managed(self):
        import src.cli

        assert (
            src.cli._is_marketplace_managed(
                "/Users/someone/Desktop/token-saver"
            )
            is False
        )

    def test_old_plugin_dir_not_marketplace_managed(self):
        import src.cli

        # Pre-marketplace layout (~/.claude/plugins/token-saver) is
        # self-updatable.
        path = os.path.join(
            os.path.expanduser("~"), ".claude", "plugins", "token-saver"
        )
        assert src.cli._is_marketplace_managed(path) is False


class TestBinScript:
    """The CLI entry point ships as two files: a POSIX script and a .cmd shim.

    ``bin/token-saver`` has a ``#!`` line, which Windows does not honour — it
    cannot be executed directly there, which is exactly why
    ``bin/token-saver.cmd`` exists.  Testing only the POSIX one left the shim
    completely unexercised until CI first ran on Windows.
    """

    @staticmethod
    def _entry_point() -> str:
        name = "token-saver.cmd" if IS_WINDOWS else "token-saver"
        return os.path.join(REPO_DIR, "bin", name)

    def test_bin_script_exists_and_executable(self):
        bin_path = os.path.join(REPO_DIR, "bin", "token-saver")
        assert os.path.exists(bin_path)
        assert os.access(bin_path, os.X_OK)

    def test_windows_shim_exists(self):
        """Present on every OS, so a POSIX-only contributor cannot delete it."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bin", "token-saver.cmd"))

    def test_bin_script_runs_version(self):
        result = subprocess.run(  # noqa: S603
            [self._entry_point(), "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_DIR,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert f"token-saver v{src.__version__}" in result.stdout


def test_explain_and_core_work_without_host_adapter_package(tmp_path):
    runtime = tmp_path / "runtime"
    shutil.copytree(
        pathlib.Path(REPO_DIR) / "src",
        runtime / "src",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    profile = tmp_path / "profile"
    profile.mkdir()
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("TOKEN_SAVER_"):
            environment.pop(name)
    environment.update(
        HOME=str(profile),
        USERPROFILE=str(profile),
        APPDATA=str(profile),
        TOKEN_SAVER_DB_DIR=str(profile),
    )
    program = """
import argparse
import pathlib
import sys
sys.path.insert(0, sys.argv[1])
from src import cli
from src import core
loaded_root = pathlib.Path(cli.__file__).resolve().parent.parent
assert loaded_root == pathlib.Path(sys.argv[1]).resolve()
assert core.should_compress("git status")
assert not core.should_compress("sudo git status")
cli.cmd_explain(argparse.Namespace(command_str="git status", format="json"))
assert "scripts.hook_pretool" not in sys.modules
"""
    result = subprocess.run(  # noqa: S603 — fixed isolated runtime probe.
        [sys.executable, "-I", "-c", program, str(runtime)],
        cwd=profile,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)
    assert decision["compressible"] is True
    assert decision["processor"] == "git"
    assert list(profile.iterdir()) == []
