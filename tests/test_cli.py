"""Tests for the token-saver CLI subcommands."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import __version__

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_cli(*args, stdin=None):
    """Run src/cli.py as a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "src.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO_DIR,
        input=stdin,
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

    def test_benchmark_show_removed_text(self):
        rc, stdout, _ = _run_cli("benchmark", "git log --oneline -50", "--show-removed")
        assert rc == 0
        assert "Removed breakdown:" in stdout
        assert "Lines:" in stdout

    def test_benchmark_show_removed_json(self):
        rc, stdout, _ = _run_cli(
            "benchmark", "git log --oneline -50", "--show-removed", "--format", "json"
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
        piped = "\n".join(f"{i:07x} commit message {i}" for i in range(50)) + "\n"
        rc, stdout, _ = _run_cli(
            "benchmark", "git log --oneline", "--stdin", "--format", "json", stdin=piped
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
        from src.diffstat import summarize

        original = "a\nb\nc\nd\ne\n"
        compressed = "a\ne\n"
        s = summarize(original, compressed)
        assert s["original_lines"] == 5
        assert s["compressed_lines"] == 2
        assert s["lines_removed"] == 3
        assert s["chars_removed"] == len(original) - len(compressed)
        assert "b" in s["removed_samples"]

    def test_summarize_added_summary_line(self):
        from src.diffstat import summarize

        original = "x\ny\nz\n"
        compressed = "x\n... (2 more)\n"
        s = summarize(original, compressed)
        assert s["lines_added"] >= 1
        assert any("more" in a for a in s["added_samples"])

    def test_summarize_no_change(self):
        from src.diffstat import summarize

        s = summarize("same\n", "same\n")
        assert s["lines_removed"] == 0
        assert s["lines_added"] == 0
        assert s["chars_removed"] == 0

    def test_format_summary_contains_sections(self):
        from src.diffstat import format_summary, summarize

        text = format_summary(summarize("a\nb\nc\n", "a\n"))
        assert "Removed breakdown:" in text
        assert "Lines:" in text
        assert "Chars:" in text


class TestMarketplaceDetection:
    def test_cache_path_is_marketplace_managed(self):
        from src.cli import _is_marketplace_managed

        path = os.path.join(
            os.path.expanduser("~"),
            ".claude",
            "plugins",
            "cache",
            "token-saver-marketplace",
            "token-saver",
        )
        assert _is_marketplace_managed(path) is True

    def test_regular_repo_not_marketplace_managed(self):
        from src.cli import _is_marketplace_managed

        assert _is_marketplace_managed("/Users/someone/Desktop/token-saver") is False

    def test_old_plugin_dir_not_marketplace_managed(self):
        from src.cli import _is_marketplace_managed

        # Pre-marketplace layout (~/.claude/plugins/token-saver) is self-updatable.
        path = os.path.join(
            os.path.expanduser("~"), ".claude", "plugins", "token-saver"
        )
        assert _is_marketplace_managed(path) is False


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
