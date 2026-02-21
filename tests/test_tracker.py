"""Tests for the savings tracker and stats CLI."""

import json
import os
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker import SavingsTracker


class TestSavingsTracker:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Override DB path for testing
        SavingsTracker.DB_DIR = self.tmp_dir
        SavingsTracker.DB_PATH = os.path.join(self.tmp_dir, "test_savings.db")
        self.tracker = SavingsTracker(session_id="test-session")

    def teardown_method(self):
        self.tracker.close()
        db_path = os.path.join(self.tmp_dir, "test_savings.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        # Clean up WAL files
        for ext in ("-wal", "-shm"):
            wal = db_path + ext
            if os.path.exists(wal):
                os.remove(wal)
        os.rmdir(self.tmp_dir)

    def test_record_and_retrieve(self):
        self.tracker.record_saving(
            command="git status",
            processor="git",
            original_size=1000,
            compressed_size=200,
            platform="claude_code",
        )
        stats = self.tracker.get_session_stats()
        assert stats["commands"] == 1
        assert stats["original"] == 1000
        assert stats["compressed"] == 200
        assert stats["saved"] == 800
        assert stats["ratio"] == 80.0

    def test_multiple_records(self):
        for i in range(5):
            self.tracker.record_saving(
                command=f"cmd {i}",
                processor="test",
                original_size=100,
                compressed_size=50,
                platform="claude_code",
            )
        stats = self.tracker.get_session_stats()
        assert stats["commands"] == 5
        assert stats["original"] == 500
        assert stats["compressed"] == 250

    def test_lifetime_stats(self):
        # First session
        self.tracker.record_saving("cmd1", "git", 1000, 200, "claude_code")

        # Second session
        tracker2 = SavingsTracker(session_id="session-2")
        tracker2.record_saving("cmd2", "test", 500, 100, "gemini_cli")

        lifetime = tracker2.get_lifetime_stats()
        assert lifetime["sessions"] == 2
        assert lifetime["commands"] == 2
        assert lifetime["original"] == 1500
        assert lifetime["compressed"] == 300
        tracker2.close()

    def test_empty_session_stats(self):
        stats = self.tracker.get_session_stats("nonexistent")
        assert stats["commands"] == 0
        assert stats["saved"] == 0
        assert stats["ratio"] == 0.0

    def test_format_stats_no_data(self):
        msg = self.tracker.format_stats_message()
        assert "[token-saver]" in msg
        assert "No compressions" in msg

    def test_format_stats_with_data(self):
        self.tracker.record_saving("git status", "git", 5000, 500, "claude_code")
        msg = self.tracker.format_stats_message()
        assert "[token-saver]" in msg
        assert "Lifetime" in msg

    def test_format_tokens(self):
        assert self.tracker._format_tokens(500) == "500 tokens"
        assert self.tracker._format_tokens(2000) == "2.0k tokens"
        assert self.tracker._format_tokens(1500000) == "1.5M tokens"

    def test_chars_to_tokens(self):
        assert self.tracker._chars_to_tokens(0) == 0
        assert self.tracker._chars_to_tokens(4) == 1
        assert self.tracker._chars_to_tokens(400) == 100
        assert self.tracker._chars_to_tokens(3) == 1  # rounds up to min 1

    def test_command_truncation(self):
        """Long commands should be truncated to 500 chars."""
        long_cmd = "x" * 1000
        self.tracker.record_saving(long_cmd, "test", 100, 50, "claude_code")
        # Should not crash
        stats = self.tracker.get_session_stats()
        assert stats["commands"] == 1

    def test_top_processors(self):
        self.tracker.record_saving("git status", "git", 1000, 200, "claude_code")
        self.tracker.record_saving("git diff", "git", 2000, 400, "claude_code")
        self.tracker.record_saving("pytest", "test", 500, 100, "claude_code")
        top = self.tracker.get_top_processors()
        assert len(top) == 2
        assert top[0]["processor"] == "git"  # More saved

    def test_concurrent_writes(self):
        """Multiple threads writing should not crash."""
        errors = []

        def write_records(n):
            try:
                for i in range(20):
                    self.tracker.record_saving(f"cmd-{n}-{i}", "test", 100, 50, "claude_code")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_records, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = self.tracker.get_session_stats()
        assert stats["commands"] == 80

    def test_db_recreation_on_corruption(self):
        """If DB is corrupted, it should be recreated."""
        self.tracker.close()
        # Corrupt the DB file
        with open(SavingsTracker.DB_PATH, "w") as f:
            f.write("not a valid sqlite database")

        # Should recreate without error
        tracker2 = SavingsTracker(session_id="recovery-test")
        tracker2.record_saving("cmd", "test", 100, 50, "claude_code")
        stats = tracker2.get_session_stats()
        assert stats["commands"] == 1
        tracker2.close()


class TestStatsCLI:
    """Tests for src/stats.py CLI script."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.original_db_dir = SavingsTracker.DB_DIR
        self.original_db_path = SavingsTracker.DB_PATH
        # Use savings.db to match what stats.py creates via TOKEN_SAVER_DB_DIR
        SavingsTracker.DB_DIR = self.tmp_dir
        SavingsTracker.DB_PATH = os.path.join(self.tmp_dir, "savings.db")
        self.stats_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src",
            "stats.py",
        )

    def teardown_method(self):
        db_path = os.path.join(self.tmp_dir, "savings.db")
        for f in (db_path, db_path + "-wal", db_path + "-shm"):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self.tmp_dir)
        SavingsTracker.DB_DIR = self.original_db_dir
        SavingsTracker.DB_PATH = self.original_db_path

    def _run_stats(self, *args):
        """Run stats.py and return stdout."""
        env = os.environ.copy()
        env["TOKEN_SAVER_DB_DIR"] = self.tmp_dir
        result = subprocess.run(  # noqa: S603, PLW1510
            [sys.executable, self.stats_script, *args],
            capture_output=True,
            text=True,
            env=env,
        )
        return result

    def _seed_data(self):
        """Insert test data into the DB."""
        tracker = SavingsTracker(session_id="test-stats")
        tracker.record_saving("git status", "git", 5000, 500, "claude_code")
        tracker.record_saving("pytest", "test", 3000, 800, "gemini_cli")
        tracker.record_saving("git diff", "git", 10000, 2000, "claude_code")
        tracker.close()

    def test_empty_db_human(self):
        result = self._run_stats()
        assert result.returncode == 0
        assert "Token-Saver Statistics" in result.stdout
        assert "No compressions" in result.stdout

    def test_empty_db_json(self):
        result = self._run_stats("--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["session"]["commands"] == 0
        assert data["lifetime"]["commands"] == 0
        assert data["top_processors"] == []

    def test_with_data_human(self):
        self._seed_data()
        result = self._run_stats()
        assert result.returncode == 0
        assert "Lifetime" in result.stdout
        assert "Commands compressed:" in result.stdout
        assert "Saved:" in result.stdout
        assert "Top Processors" in result.stdout
        assert "git" in result.stdout

    def test_with_data_json(self):
        self._seed_data()
        result = self._run_stats("--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["lifetime"]["commands"] == 3
        assert data["lifetime"]["original"] == 18000
        assert data["lifetime"]["compressed"] == 3300
        assert data["lifetime"]["saved"] == 14700
        assert len(data["top_processors"]) == 2
        assert data["top_processors"][0]["processor"] == "git"

    def test_top_processors_order(self):
        self._seed_data()
        result = self._run_stats("--json")
        data = json.loads(result.stdout)
        # git saved 12500 (5000-500 + 10000-2000), test saved 2200 (3000-800)
        assert data["top_processors"][0]["processor"] == "git"
        assert data["top_processors"][1]["processor"] == "test"
