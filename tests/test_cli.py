"""Tests for the token-saver CLI subcommands."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import __version__

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_cli(*args):
    """Run src/cli.py as a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "src.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO_DIR,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


class TestVersionCommand:
    def test_prints_version(self):
        rc, stdout, _ = _run_cli("version")
        assert rc == 0
        assert f"token-saver v{__version__}" in stdout

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
    def test_stats_human_readable(self):
        rc, stdout, _ = _run_cli("stats")
        assert rc == 0
        assert "Token-Saver Savings" in stdout

    def test_stats_json(self):
        rc, stdout, _ = _run_cli("stats", "--json")
        assert rc == 0
        data = json.loads(stdout)
        assert "session" in data
        assert "lifetime" in data


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
        rc, stdout, _ = _run_cli("benchmark", "git diff HEAD", "--dry-run", "--format", "json")
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


class TestBinScript:
    def test_bin_script_exists_and_executable(self):
        bin_path = os.path.join(REPO_DIR, "bin", "token-saver")
        assert os.path.exists(bin_path)
        assert os.access(bin_path, os.X_OK)

    def test_bin_script_runs_version(self):
        bin_path = os.path.join(REPO_DIR, "bin", "token-saver")
        result = subprocess.run(  # noqa: S603
            [bin_path, "version"],
            capture_output=True,
            text=True,
            cwd=REPO_DIR,
            check=False,
        )
        assert result.returncode == 0
        assert f"token-saver v{__version__}" in result.stdout
