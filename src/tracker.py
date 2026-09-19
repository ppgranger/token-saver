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

"""SQLite-based savings tracker with thread safety and auto-pruning."""

import contextlib
import os
import sqlite3
import threading
import time

import src
from src import config
from src import stats_formatting

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS savings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        session_id TEXT NOT NULL,
        command TEXT NOT NULL,
        processor TEXT NOT NULL,
        original_size INTEGER NOT NULL,
        compressed_size INTEGER NOT NULL,
        platform TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        first_seen REAL NOT NULL,
        last_seen REAL NOT NULL,
        total_original INTEGER DEFAULT 0,
        total_compressed INTEGER DEFAULT 0,
        command_count INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS mismatches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        session_id TEXT NOT NULL,
        command TEXT NOT NULL,
        processor TEXT NOT NULL,
        original_size INTEGER NOT NULL,
        platform TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_savings_session ON savings(session_id);
    CREATE INDEX IF NOT EXISTS idx_savings_timestamp ON savings(timestamp);
    CREATE INDEX IF NOT EXISTS idx_mismatches_ts ON mismatches(timestamp);
"""


class SavingsTracker:
    """Track token savings in a local SQLite database.

    Thread-safe via a reentrant lock on all DB operations. Automatically prunes
    old records on startup.

    Attributes:
        DB_DIR: Optional class-level override for the database directory.
        DB_PATH: Optional class-level override for the database file.
        session_id: Session identifier attached to recorded events.
        prune_days: Age in days after which records may be pruned.
        conn: SQLite connection protected by the shared reentrant lock.
    """

    @staticmethod
    def _default_db_dir():
        """Resolve the database directory for a newly constructed tracker.

        Returns:
            The environment override or the platform-specific data directory.
        """
        return os.environ.get("TOKEN_SAVER_DB_DIR") or src.data_dir()

    @staticmethod
    def _default_db_path(db_dir: str | None = None):
        """Build the database path from the current environment.

        Args:
            db_dir: Database directory override, or None to resolve the current
                default.

        Returns:
            Path of savings.db within the selected directory.
        """
        return os.path.join(
            db_dir or SavingsTracker._default_db_dir(), "savings.db"
        )

    # Class-level defaults — can be overridden (e.g. by stats.py for testing)
    DB_DIR: str | None = None
    DB_PATH: str | None = None

    _lock = threading.RLock()

    @staticmethod
    def _fallback_session_id() -> str:
        """Generate a session ID from the parent process.

        Each Bash command spawns a fresh wrap.py process, so a per-process
        random id would record every command as its own one-command session.
        Keying off the parent process (the shell that launched wrap.py) groups
        commands from the same shell together instead of fragmenting them.

        Returns:
            A stable label derived from the parent process ID.
        """
        return f"ppid-{os.getppid()}"

    def __init__(
        self, session_id: str | None = None, prune_days: int | None = None
    ):
        """Open the savings database and initialize this tracking session.

        Args:
            session_id: Explicit session ID, or None to use the environment or
                parent process.
            prune_days: Retention period in days, or None to read db_prune_days.

        Raises:
            OSError: The database directory cannot be created.
            sqlite3.Error: The database cannot be opened or initialized after
                recovery.
        """
        self.session_id = (
            session_id
            or os.environ.get("TOKEN_SAVER_SESSION")
            or self._fallback_session_id()
        )
        # Defaulting from config rather than a literal: `db_prune_days` is
        # documented in the README as the stats-retention knob, but nothing
        # ever read it — every caller took the hardcoded 90 days.  An explicit
        # argument still wins, which is what the tests use.
        self.prune_days = (
            config.get("db_prune_days") if prune_days is None else prune_days
        )
        # Explicit class overrides remain supported, but resolved defaults
        # belong
        # to this instance: caching them on the class ignores later environment
        # changes and can direct a new session into an earlier session's
        # database.
        self._db_dir: str = self.DB_DIR or self._default_db_dir()
        self._db_path: str = self.DB_PATH or self._default_db_path(self._db_dir)
        os.makedirs(self._db_dir, exist_ok=True)
        self._open_connection()
        self._init_db()
        self._maybe_prune()

    def _remove_db_files(self):
        """Delete the DB and its WAL/SHM sidecars.

        In WAL mode the -wal and -shm files hold committed-but-uncheckpointed
        data; removing only the main .db can leave stale sidecars that re-
        corrupt the freshly created database.

        Any open connection is closed first.  ``sqlite3.connect()`` succeeds on
        a corrupt file — it is the first statement that raises — so the caller
        arrives here holding an open handle, and Windows refuses to unlink a
        file that is still open (``WinError 32``).  The delete would then be
        swallowed by the suppress below, the corrupt file would survive, and
        recovery would fail on the very next statement.  POSIX unlink semantics
        hide all of this, which is why it surfaced only on the Windows runner.
        """
        conn = getattr(self, "conn", None)
        if conn is not None:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        for suffix in ("", "-wal", "-shm"):
            with contextlib.suppress(OSError):
                os.remove(self._db_path + suffix)

    def _open_connection(self):
        """Open SQLite connection, handling corrupted DB files."""
        try:
            self.conn = sqlite3.connect(
                self._db_path,
                timeout=10,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            # File exists but is corrupted
            self._remove_db_files()
            self.conn = sqlite3.connect(
                self._db_path,
                timeout=10,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")

    def _init_db(self):
        """Create all tables and indexes with one schema, including recovery."""
        with self._lock:
            try:
                self.conn.executescript(_SCHEMA)
            except sqlite3.DatabaseError:
                # Corrupted DB — recreate (drop WAL/SHM sidecars too)
                self._remove_db_files()
                self._open_connection()
                self.conn.executescript(_SCHEMA)

    def _maybe_prune(self):
        """Prune old records if the DB has grown."""
        try:
            with self._lock:
                cutoff = time.time() - (self.prune_days * 86400)
                self.conn.execute(
                    "DELETE FROM savings WHERE timestamp < ?", (cutoff,)
                )
                self.conn.execute(
                    "DELETE FROM sessions WHERE last_seen < ?", (cutoff,)
                )
                self.conn.execute(
                    "DELETE FROM mismatches WHERE timestamp < ?", (cutoff,)
                )
                self.conn.commit()
        except sqlite3.Error:
            pass

    def record_saving(
        self,
        command: str,
        processor: str,
        original_size: int,
        compressed_size: int,
        platform: str,
    ):
        """Record a single compression event.

        Args:
            command: Shell command text associated with the captured output.
            processor: Stable name of the processor that handled the output.
            original_size: Original output length in characters.
            compressed_size: Compressed output length in characters.
            platform: Name of the host integration recording the event.
        """
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO savings (timestamp, session_id, command, "
                    "processor, original_size, compressed_size, platform) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        now,
                        self.session_id,
                        command[:500],
                        processor,
                        original_size,
                        compressed_size,
                        platform,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO sessions (session_id, first_seen, last_seen,
                        total_original, total_compressed, command_count)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(session_id) DO UPDATE SET
                        last_seen = ?,
                        total_original = total_original + ?,
                        total_compressed = total_compressed + ?,
                        command_count = command_count + 1
                """,
                    (
                        self.session_id,
                        now,
                        now,
                        original_size,
                        compressed_size,
                        now,
                        original_size,
                        compressed_size,
                    ),
                )
                self.conn.commit()
            except sqlite3.Error:
                with contextlib.suppress(sqlite3.Error):
                    self.conn.rollback()

    def record_mismatch(
        self, command: str, processor: str, original_size: int, platform: str
    ) -> None:
        """Record a processor-mismatch event (O3).

        A specialized processor matched the command and ran, but did not
        compress enough on its own (output fell back to generic or passthrough).
        Surfacing these lets weak processors be found empirically.

        Args:
            command: Shell command text associated with the captured output.
            processor: Stable name of the processor that handled the output.
            original_size: Original output length in characters.
            platform: Name of the host integration recording the event.
        """
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO mismatches "
                    "(timestamp, session_id, command, processor, "
                    "original_size, platform) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        now,
                        self.session_id,
                        command[:500],
                        processor,
                        original_size,
                        platform,
                    ),
                )
                self.conn.commit()
            except sqlite3.Error:
                with contextlib.suppress(sqlite3.Error):
                    self.conn.rollback()

    def get_processor_mismatches(self, limit: int = 10) -> list[dict]:
        """Return processors that most often ran without compressing enough.

        Args:
            limit: Maximum number of aggregate rows to return.

        Returns:
            Processor/count/original-size mappings, or an empty list on a
            database error.
        """
        with self._lock:
            try:
                rows = self.conn.execute(
                    """
                    SELECT processor,
                           COUNT(*) as count,
                           SUM(original_size) as total_original
                    FROM mismatches
                    GROUP BY processor
                    ORDER BY count DESC
                    LIMIT ?
                """,
                    (limit,),
                ).fetchall()
            except sqlite3.Error:
                return []
        return [
            {
                "processor": r["processor"],
                "count": r["count"],
                "total_original": r["total_original"],
            }
            for r in rows
        ]

    def get_session_stats(self, session_id: str | None = None) -> dict:
        """Get stats for a session.

        Args:
            session_id: Session identifier, or None to use the current session.

        Returns:
            Command count, original/compressed/saved characters, and savings
            percentage.
        """
        sid = session_id or self.session_id
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (sid,)
            ).fetchone()
        if not row:
            return {
                "commands": 0,
                "original": 0,
                "compressed": 0,
                "saved": 0,
                "ratio": 0.0,
            }
        original = row["total_original"]
        compressed = row["total_compressed"]
        saved = original - compressed
        ratio = (saved / original * 100) if original > 0 else 0.0
        return {
            "commands": row["command_count"],
            "original": original,
            "compressed": compressed,
            "saved": saved,
            "ratio": round(ratio, 1),
        }

    def get_lifetime_stats(self) -> dict:
        """Get aggregated stats across all sessions.

        Returns:
            Session and command counts, character totals, and savings
            percentage.
        """
        with self._lock:
            row = self.conn.execute("""
                SELECT
                    COUNT(*) as session_count,
                    COALESCE(SUM(total_original), 0) as total_original,
                    COALESCE(SUM(total_compressed), 0) as total_compressed,
                    COALESCE(SUM(command_count), 0) as total_commands
                FROM sessions
            """).fetchone()
        original = row["total_original"]
        compressed = row["total_compressed"]
        saved = original - compressed
        ratio = (saved / original * 100) if original > 0 else 0.0
        return {
            "sessions": row["session_count"],
            "commands": row["total_commands"],
            "original": original,
            "compressed": compressed,
            "saved": saved,
            "ratio": round(ratio, 1),
        }

    def get_top_commands(self, limit: int = 10) -> list[dict]:
        """Get commands with the largest total character reduction.

        Args:
            limit: Maximum number of aggregate rows to return.

        Returns:
            Command aggregates with counts, character totals, and savings
            percentages.
        """
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT command,
                       COUNT(*) as count,
                       SUM(original_size) as total_original,
                       SUM(compressed_size) as total_compressed,
                       SUM(original_size - compressed_size) as total_saved
                FROM savings
                GROUP BY command
                ORDER BY total_saved DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
        results = []
        for r in rows:
            orig = r["total_original"]
            ratio = (
                ((orig - r["total_compressed"]) / orig * 100)
                if orig > 0
                else 0.0
            )
            results.append(
                {
                    "command": r["command"],
                    "count": r["count"],
                    "total_original": orig,
                    "total_compressed": r["total_compressed"],
                    "total_saved": r["total_saved"],
                    "avg_ratio": round(ratio, 1),
                }
            )
        return results

    def get_top_processors(self, limit: int = 5) -> list[dict]:
        """Get the most effective processors.

        Args:
            limit: Maximum number of aggregate rows to return.

        Returns:
            Processor names, command counts, and saved character totals.
        """
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT processor,
                       COUNT(*) as count,
                       SUM(original_size - compressed_size) as total_saved
                FROM savings
                GROUP BY processor
                ORDER BY total_saved DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
        return [
            {
                "processor": r["processor"],
                "count": r["count"],
                "saved": r["total_saved"],
            }
            for r in rows
        ]

    @staticmethod
    def _chars_to_tokens(n: int) -> int:
        """Estimate token count from character count.

        Args:
            n: Nonnegative count to format or convert.

        Returns:
            A rounded token estimate using the configured characters-per-token
            ratio.
        """
        return stats_formatting.estimate_tokens(
            n, config.get("chars_per_token")
        )

    @staticmethod
    def _format_tokens(n: int) -> str:
        """Human-readable token count.

        Args:
            n: Nonnegative count to format or convert.

        Returns:
            Human-readable estimated-token text with a unit suffix.
        """
        return stats_formatting.format_tokens(n)

    def format_stats_message(self) -> str:
        """Preserve the historical summary API through the presentation module.

        Returns:
            One line summarizing lifetime and current-session estimated savings.
        """
        return stats_formatting.format_stats_message(
            self.get_lifetime_stats(),
            self.get_session_stats(),
            chars_per_token=config.get("chars_per_token"),
        )

    def close(self):
        """Close the SQLite connection without surfacing cleanup errors."""
        with self._lock, contextlib.suppress(sqlite3.Error):
            self.conn.close()
