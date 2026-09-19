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

"""Tests for the savings tracker and stats CLI."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.tracker
from src import config


def _connection_is_open(conn) -> bool:
    """True if ``conn`` still accepts statements (closed connections raise)."""
    if conn is None:
        return False
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return False
    except sqlite3.Error:
        # Corrupt but still open — which is exactly the state we care about.
        return True
    return True


class TestSavingsTracker:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.original_db_dir = src.tracker.SavingsTracker.DB_DIR
        self.original_db_path = src.tracker.SavingsTracker.DB_PATH
        # Override DB path for testing
        src.tracker.SavingsTracker.DB_DIR = self.tmp_dir
        src.tracker.SavingsTracker.DB_PATH = os.path.join(
            self.tmp_dir, "test_savings.db"
        )
        self.tracker = src.tracker.SavingsTracker(session_id="test-session")

    def teardown_method(self):
        self.tracker.close()
        # rmtree(ignore_errors) rather than remove()+rmdir(): a test that leaves
        # a stray file makes rmdir raise, and on Windows an unclosed sqlite
        # handle makes remove() raise WinError 32.  Neither is worth failing
        # teardown over — the temp dir is disposable.
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        src.tracker.SavingsTracker.DB_DIR = self.original_db_dir
        src.tracker.SavingsTracker.DB_PATH = self.original_db_path

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
        tracker2 = src.tracker.SavingsTracker(session_id="session-2")
        tracker2.record_saving("cmd2", "test", 500, 100, "antigravity_cli")

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

    def test_format_stats_with_data(self, monkeypatch):
        self.tracker.record_saving(
            "git status", "git", 5000, 500, "claude_code"
        )
        monkeypatch.setattr(config, "get", lambda key: 4)
        assert self.tracker.format_stats_message() == (
            "[token-saver] | Lifetime: 1 cmds, 1.1k tokens saved (90.0%)"
            " | Session: 1 cmds, 1.1k tokens saved (90.0%)"
        )

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
        self.tracker.record_saving(
            "git status", "git", 1000, 200, "claude_code"
        )
        self.tracker.record_saving("git diff", "git", 2000, 400, "claude_code")
        self.tracker.record_saving("pytest", "test", 500, 100, "claude_code")
        top = self.tracker.get_top_processors()
        assert len(top) == 2
        assert top[0]["processor"] == "git"  # More saved

    def test_record_and_retrieve_mismatches(self):
        self.tracker.record_mismatch("docker ps", "docker", 1000, "claude_code")
        self.tracker.record_mismatch("docker ps", "docker", 1200, "claude_code")
        self.tracker.record_mismatch(
            "kubectl get pods", "kubectl", 800, "claude_code"
        )
        rows = self.tracker.get_processor_mismatches()
        assert len(rows) == 2
        assert rows[0]["processor"] == "docker"
        assert rows[0]["count"] == 2
        assert rows[0]["total_original"] == 2200

    def test_mismatches_empty_by_default(self):
        assert self.tracker.get_processor_mismatches() == []

    def test_top_commands_grouping_and_order(self):
        """get_top_commands groups by command and orders by total_saved DESC."""
        self.tracker.record_saving(
            "git status", "git", 1000, 200, "claude_code"
        )
        self.tracker.record_saving(
            "git status", "git", 1000, 300, "claude_code"
        )
        self.tracker.record_saving("git diff", "git", 5000, 1000, "claude_code")
        self.tracker.record_saving("pytest", "test", 500, 100, "claude_code")
        top = self.tracker.get_top_commands()
        assert len(top) == 3
        # git diff saved 4000, git status saved 1500, pytest saved 400
        assert top[0]["command"] == "git diff"
        assert top[0]["total_saved"] == 4000
        assert top[0]["count"] == 1
        assert top[1]["command"] == "git status"
        assert top[1]["total_saved"] == 1500
        assert top[1]["count"] == 2
        assert top[2]["command"] == "pytest"

    def test_top_commands_limit(self):
        """get_top_commands respects the limit parameter."""
        for i in range(5):
            self.tracker.record_saving(
                f"cmd-{i}", "test", 100 * (i + 1), 10, "claude_code"
            )
        top = self.tracker.get_top_commands(limit=3)
        assert len(top) == 3

    def test_top_commands_avg_ratio(self):
        """get_top_commands computes avg_ratio correctly."""
        self.tracker.record_saving(
            "git status", "git", 1000, 200, "claude_code"
        )
        top = self.tracker.get_top_commands()
        assert top[0]["avg_ratio"] == 80.0

    def test_concurrent_writes(self):
        """Multiple threads writing should not crash."""
        errors = []

        def write_records(n):
            try:
                for i in range(20):
                    self.tracker.record_saving(
                        f"cmd-{n}-{i}", "test", 100, 50, "claude_code"
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=write_records, args=(i,)) for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = self.tracker.get_session_stats()
        assert stats["commands"] == 80

    def test_session_id_from_env(self):
        """TOKEN_SAVER_SESSION env var should set the session ID."""
        os.environ["TOKEN_SAVER_SESSION"] = "env-session-42"  # noqa: S105
        try:
            tracker = src.tracker.SavingsTracker()
            assert tracker.session_id == "env-session-42"
            tracker.close()
        finally:
            del os.environ["TOKEN_SAVER_SESSION"]

    def test_fallback_session_id_is_stable_across_instances(self):
        """Share a process session ID when no explicit ID is configured.

        Each Bash command spawns a fresh wrap.py; a per-process random id would
        record every command as its own session.  The ppid-based fallback keeps
        commands from the same shell grouped together.
        """
        os.environ.pop("TOKEN_SAVER_SESSION", None)
        t1 = src.tracker.SavingsTracker()
        t2 = src.tracker.SavingsTracker()
        try:
            assert t1.session_id == t2.session_id
            assert t1.session_id.startswith("ppid-")
        finally:
            t1.close()
            t2.close()

    def test_shared_session_aggregates(self):
        """Multiple trackers with the same session_id should aggregate."""
        t1 = src.tracker.SavingsTracker(session_id="shared-session")
        t1.record_saving("git status", "git", 1000, 200, "claude_code")
        t1.close()

        t2 = src.tracker.SavingsTracker(session_id="shared-session")
        t2.record_saving("git diff", "git", 2000, 400, "claude_code")

        stats = t2.get_session_stats()
        assert stats["commands"] == 2
        assert stats["original"] == 3000
        assert stats["compressed"] == 600
        assert stats["saved"] == 2400

        # Lifetime should show 1 session, not 2
        lifetime = t2.get_lifetime_stats()
        assert lifetime["sessions"] == 1
        assert lifetime["commands"] == 2
        t2.close()

    def test_session_stats_isolated(self):
        """Different session IDs should have independent stats."""
        t1 = src.tracker.SavingsTracker(session_id="session-A")
        t1.record_saving("cmd1", "git", 1000, 200, "claude_code")
        t1.close()

        t2 = src.tracker.SavingsTracker(session_id="session-B")
        t2.record_saving("cmd2", "test", 500, 100, "claude_code")

        a_stats = t2.get_session_stats("session-A")
        b_stats = t2.get_session_stats("session-B")
        assert a_stats["commands"] == 1
        assert a_stats["original"] == 1000
        assert b_stats["commands"] == 1
        assert b_stats["original"] == 500

        lifetime = t2.get_lifetime_stats()
        assert lifetime["sessions"] == 2
        assert lifetime["commands"] == 2
        t2.close()

    def test_db_recreation_on_corruption(self):
        """If DB is corrupted, it should be recreated."""
        self.tracker.close()
        # Corrupt the DB file
        with open(
            src.tracker.SavingsTracker.DB_PATH, "w", encoding="utf-8"
        ) as f:
            f.write("not a valid sqlite database")

        # Should recreate without error
        tracker2 = src.tracker.SavingsTracker(session_id="recovery-test")
        tracker2.record_saving("cmd", "test", 100, 50, "claude_code")
        stats = tracker2.get_session_stats()
        assert stats["commands"] == 1
        tracker2.close()

    def test_schema_recovery_recreates_tables_indexes_and_wal(self):
        schema_query = (
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index') ORDER BY type, name"
        )
        expected_schema = [
            tuple(row) for row in self.tracker.conn.execute(schema_query)
        ]
        # This remains a valid SQLite file but has an incompatible savings
        # table. Opening succeeds; creating its required indexes must fail.
        self.tracker.conn.executescript(
            "DROP TABLE savings; CREATE TABLE savings (id INTEGER);"
        )
        self.tracker.close()

        recovered = src.tracker.SavingsTracker(session_id="schema-recovery")
        try:
            actual_schema = [
                tuple(row) for row in recovered.conn.execute(schema_query)
            ]
            assert actual_schema == expected_schema
            assert (
                recovered.conn.execute("PRAGMA journal_mode").fetchone()[0]
                == "wal"
            )
            recovered.record_saving("git status", "git", 1000, 200, "claude")
            recovered.record_mismatch("docker ps", "docker", 1000, "claude")
            assert recovered.get_session_stats()["saved"] == 800
            assert recovered.get_processor_mismatches()[0]["count"] == 1
        finally:
            recovered.close()

    def test_corruption_recovery_closes_the_db_before_unlinking(self):
        """The handle must be closed *before* the file is deleted.

        ``sqlite3.connect()`` succeeds on a corrupt file — the first statement
        is what raises — so recovery arrives at the delete still holding an
        open connection.  POSIX happily unlinks an open file, so the leak is
        invisible there and the test above passes either way.  Windows returns
        ``WinError 32``, the suppressed delete silently does nothing, and the
        corrupt file survives to break the reconnect.

        Asserting on the ordering rather than the platform behaviour is what
        makes this catch the bug on Linux and macOS too.
        """
        self.tracker.close()
        with open(
            src.tracker.SavingsTracker.DB_PATH, "w", encoding="utf-8"
        ) as f:
            f.write("not a valid sqlite database")

        open_at_delete = []
        real_remove = os.remove

        def spy_remove(path):
            tracker = getattr(src.tracker.SavingsTracker, "_recovering", None)
            if tracker is not None:
                open_at_delete.append(_connection_is_open(tracker.conn))
            return real_remove(path)

        original_remove_files = src.tracker.SavingsTracker._remove_db_files

        def traced_remove_files(inner_self):
            src.tracker.SavingsTracker._recovering = inner_self
            try:
                return original_remove_files(inner_self)
            finally:
                src.tracker.SavingsTracker._recovering = None

        with (
            mock.patch.object(
                src.tracker.SavingsTracker,
                "_remove_db_files",
                traced_remove_files,
            ),
            mock.patch("src.tracker.os.remove", spy_remove),
        ):
            tracker2 = src.tracker.SavingsTracker(session_id="recovery-order")

        try:
            assert open_at_delete, (
                "recovery never tried to delete the corrupt database"
            )
            assert not any(open_at_delete), (
                "the sqlite connection was still open when the fi"
                "le was unlinked — Windows would refuse the delet"
                "e and leave the corrupt DB in place"
            )
        finally:
            tracker2.close()


class TestTrackerPaths:
    def test_environment_directory_applies_to_direct_tracker_users(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_DIR", None)
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_PATH", None)
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(tmp_path))

        tracker = src.tracker.SavingsTracker(session_id="isolated")
        try:
            tracker.record_saving("git status", "git", 1000, 100, "claude_code")
            assert tracker.get_session_stats()["saved"] == 900
            assert tracker._db_path == str(tmp_path / "savings.db")
            assert (tmp_path / "savings.db").is_file()
        finally:
            tracker.close()

    def test_default_paths_are_resolved_for_each_instance(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_DIR", None)
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_PATH", None)
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(first_dir))
        first = src.tracker.SavingsTracker(session_id="same-session")
        try:
            first.record_saving("git status", "git", 1000, 100, "claude_code")
        finally:
            first.close()

        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(second_dir))
        second = src.tracker.SavingsTracker(session_id="same-session")
        try:
            assert second._db_path == str(second_dir / "savings.db")
            assert second.get_lifetime_stats()["commands"] == 0
            assert src.tracker.SavingsTracker.DB_DIR is None
            assert src.tracker.SavingsTracker.DB_PATH is None
        finally:
            second.close()

    def test_directory_override_controls_default_filename(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_DIR", str(tmp_path))
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_PATH", None)
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(tmp_path / "unused"))

        tracker = src.tracker.SavingsTracker(session_id="directory-override")
        try:
            assert tracker._db_path == str(tmp_path / "savings.db")
            assert not (tmp_path / "unused").exists()
        finally:
            tracker.close()

    def test_stats_calls_do_not_retain_environment_paths(
        self, tmp_path, monkeypatch, capsys
    ):
        import src
        from src import stats

        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_DIR", None)
        monkeypatch.setattr(src.tracker.SavingsTracker, "DB_PATH", None)
        monkeypatch.setattr(sys, "argv", ["stats", "--json"])
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        default_dir = tmp_path / "default"
        monkeypatch.setattr(src, "data_dir", lambda: str(default_dir))
        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(first_dir))
        tracker = src.tracker.SavingsTracker(session_id="stats-paths")
        try:
            tracker.record_saving("git status", "git", 1000, 100, "claude_code")
        finally:
            tracker.close()

        stats.main()
        assert json.loads(capsys.readouterr().out)["lifetime"]["commands"] == 1
        assert src.tracker.SavingsTracker.DB_DIR is None
        assert src.tracker.SavingsTracker.DB_PATH is None

        monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(second_dir))
        stats.main()
        assert json.loads(capsys.readouterr().out)["lifetime"]["commands"] == 0
        assert (second_dir / "savings.db").is_file()

        monkeypatch.delenv("TOKEN_SAVER_DB_DIR")
        stats.main()
        assert json.loads(capsys.readouterr().out)["lifetime"]["commands"] == 0
        assert (default_dir / "savings.db").is_file()
        assert src.tracker.SavingsTracker.DB_DIR is None
        assert src.tracker.SavingsTracker.DB_PATH is None


class TestStatsCLI:
    """Tests for src/stats.py CLI script."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.original_db_dir = src.tracker.SavingsTracker.DB_DIR
        self.original_db_path = src.tracker.SavingsTracker.DB_PATH
        # Use savings.db to match what stats.py creates via TOKEN_SAVER_DB_DIR
        src.tracker.SavingsTracker.DB_DIR = self.tmp_dir
        src.tracker.SavingsTracker.DB_PATH = os.path.join(
            self.tmp_dir, "savings.db"
        )
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
        src.tracker.SavingsTracker.DB_DIR = self.original_db_dir
        src.tracker.SavingsTracker.DB_PATH = self.original_db_path

    def _run_stats(self, *args):
        """Run stats.py and return stdout."""
        env = os.environ.copy()
        env["TOKEN_SAVER_DB_DIR"] = self.tmp_dir
        result = subprocess.run(  # noqa: S603, PLW1510
            [sys.executable, self.stats_script, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        return result

    def _seed_data(self):
        """Insert test data into the DB."""
        tracker = src.tracker.SavingsTracker(session_id="test-stats")
        tracker.record_saving("git status", "git", 5000, 500, "claude_code")
        tracker.record_saving("pytest", "test", 3000, 800, "antigravity_cli")
        tracker.record_saving("git diff", "git", 10000, 2000, "claude_code")
        tracker.close()

    def test_empty_db_human(self):
        result = self._run_stats()
        assert result.returncode == 0
        assert "Token-Saver Savings" in result.stdout
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
        assert "Token-Saver Savings" in result.stdout
        assert "Total commands:" in result.stdout
        assert "Tokens saved:" in result.stdout
        assert "By Command" in result.stdout
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
        # top_commands should be present
        assert "top_commands" in data
        assert len(data["top_commands"]) > 0
        assert "command" in data["top_commands"][0]
        assert "total_saved" in data["top_commands"][0]
        assert "avg_ratio" in data["top_commands"][0]

    def test_top_processors_order(self):
        self._seed_data()
        result = self._run_stats("--json")
        data = json.loads(result.stdout)
        # git saved 12500 (5000-500 + 10000-2000), test saved 2200 (3000-800)
        assert data["top_processors"][0]["processor"] == "git"
        assert data["top_processors"][1]["processor"] == "test"

    def test_explicit_arguments_select_session_without_process_arguments(
        self, monkeypatch, capsys
    ):
        from src import stats

        self._seed_data()
        tracker = src.tracker.SavingsTracker(session_id="selected")
        try:
            tracker.record_saving("git diff", "git", 2000, 400, "claude_code")
        finally:
            tracker.close()
        original_argv = ["host-app", "--session", "unrelated"]
        monkeypatch.setattr(sys, "argv", original_argv)
        arguments = ["--json", "--session", "selected"]

        stats.main(arguments)

        data = json.loads(capsys.readouterr().out)
        assert data["session"]["commands"] == 1
        assert data["session"]["saved"] == 1600
        assert data["lifetime"]["commands"] == 4
        assert sys.argv is original_argv
        assert sys.argv == ["host-app", "--session", "unrelated"]
        assert arguments == ["--json", "--session", "selected"]

    def test_database_is_closed_when_statistics_query_fails(self):
        from src import stats

        tracker = src.tracker.SavingsTracker(session_id="failed-query")
        with (
            mock.patch.object(
                stats.tracker_lib, "SavingsTracker", return_value=tracker
            ),
            mock.patch.object(
                tracker,
                "get_lifetime_stats",
                side_effect=sqlite3.OperationalError("fixture query failure"),
            ),
            pytest.raises(sqlite3.OperationalError, match="fixture query"),
        ):
            stats.main(["--json"])
        assert not _connection_is_open(tracker.conn)


class TestPruneRetention:
    """`db_prune_days` is documented in the README but was never read.

    Every caller got the hardcoded 90 days, so configuring retention did
    nothing at all.
    """

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.original_db_dir = src.tracker.SavingsTracker.DB_DIR
        self.original_db_path = src.tracker.SavingsTracker.DB_PATH
        src.tracker.SavingsTracker.DB_DIR = self.tmp_dir
        src.tracker.SavingsTracker.DB_PATH = os.path.join(
            self.tmp_dir, "prune.db"
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        src.tracker.SavingsTracker.DB_DIR = self.original_db_dir
        src.tracker.SavingsTracker.DB_PATH = self.original_db_path

    def test_retention_defaults_to_the_configured_value(self, monkeypatch):
        monkeypatch.setattr(
            config, "get", lambda key: 7 if key == "db_prune_days" else None
        )
        tracker = src.tracker.SavingsTracker(session_id="s")
        try:
            assert tracker.prune_days == 7
        finally:
            tracker.close()

    def test_explicit_argument_still_wins(self):
        tracker = src.tracker.SavingsTracker(session_id="s", prune_days=3)
        try:
            assert tracker.prune_days == 3
        finally:
            tracker.close()

    def test_rows_older_than_retention_are_pruned(self):
        tracker = src.tracker.SavingsTracker(session_id="s", prune_days=30)
        tracker.record_saving(
            command="git status",
            processor="git",
            original_size=1000,
            compressed_size=100,
            platform="claude_code",
        )
        # Backdate the row past the retention window, then reopen: pruning
        # runs on construction.
        cutoff = time.time() - (31 * 86400)
        tracker.conn.execute("UPDATE savings SET timestamp = ?", (cutoff,))
        tracker.conn.commit()
        tracker.close()

        reopened = src.tracker.SavingsTracker(session_id="s", prune_days=30)
        try:
            rows = reopened.conn.execute(
                "SELECT COUNT(*) FROM savings"
            ).fetchone()[0]
            assert rows == 0
        finally:
            reopened.close()

    def test_rows_inside_retention_survive(self):
        tracker = src.tracker.SavingsTracker(session_id="s", prune_days=30)
        tracker.record_saving(
            command="git status",
            processor="git",
            original_size=1000,
            compressed_size=100,
            platform="claude_code",
        )
        cutoff = time.time() - (5 * 86400)
        tracker.conn.execute("UPDATE savings SET timestamp = ?", (cutoff,))
        tracker.conn.commit()
        tracker.close()

        reopened = src.tracker.SavingsTracker(session_id="s", prune_days=30)
        try:
            rows = reopened.conn.execute(
                "SELECT COUNT(*) FROM savings"
            ).fetchone()[0]
            assert rows == 1
        finally:
            reopened.close()
