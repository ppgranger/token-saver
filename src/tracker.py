"""SQLite-based savings tracker with thread safety and auto-pruning."""

import contextlib
import os
import sqlite3
import threading
import time
import uuid


class SavingsTracker:
    """Track token savings in a local SQLite database.

    Thread-safe via a reentrant lock on all DB operations.
    Automatically prunes old records on startup.
    """

    @staticmethod
    def _default_db_dir():
        from src import data_dir  # noqa: PLC0415

        return data_dir()

    @staticmethod
    def _default_db_path():
        return os.path.join(SavingsTracker._default_db_dir(), "savings.db")

    # Class-level defaults — can be overridden (e.g. by stats.py for testing)
    DB_DIR = None
    DB_PATH = None

    _lock = threading.RLock()

    def __init__(self, session_id: str | None = None, prune_days: int = 90):
        self.session_id = session_id or os.environ.get(
            "TOKEN_SAVER_SESSION", str(uuid.uuid4())[:12]
        )
        self.prune_days = prune_days
        # Resolve DB paths — use overridden class vars if set, else compute from data_dir()
        if self.DB_DIR is None:
            SavingsTracker.DB_DIR = self._default_db_dir()
        if self.DB_PATH is None:
            SavingsTracker.DB_PATH = self._default_db_path()
        os.makedirs(self.DB_DIR, exist_ok=True)
        self._open_connection()
        self._init_db()
        self._maybe_prune()

    def _open_connection(self):
        """Open SQLite connection, handling corrupted DB files."""
        try:
            self.conn = sqlite3.connect(
                self.DB_PATH,
                timeout=10,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            # File exists but is corrupted
            with contextlib.suppress(OSError):
                os.remove(self.DB_PATH)
            self.conn = sqlite3.connect(
                self.DB_PATH,
                timeout=10,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")

    def _init_db(self):
        with self._lock:
            try:
                self.conn.executescript("""
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
                    CREATE INDEX IF NOT EXISTS idx_savings_session ON savings(session_id);
                    CREATE INDEX IF NOT EXISTS idx_savings_timestamp ON savings(timestamp);
                """)
            except sqlite3.DatabaseError:
                # Corrupted DB — recreate
                self.conn.close()
                with contextlib.suppress(OSError):
                    os.remove(self.DB_PATH)
                self.conn = sqlite3.connect(self.DB_PATH, timeout=10, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                self.conn.executescript("""
                    CREATE TABLE savings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        session_id TEXT NOT NULL,
                        command TEXT NOT NULL,
                        processor TEXT NOT NULL,
                        original_size INTEGER NOT NULL,
                        compressed_size INTEGER NOT NULL,
                        platform TEXT NOT NULL
                    );
                    CREATE TABLE sessions (
                        session_id TEXT PRIMARY KEY,
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL,
                        total_original INTEGER DEFAULT 0,
                        total_compressed INTEGER DEFAULT 0,
                        command_count INTEGER DEFAULT 0
                    );
                """)

    def _maybe_prune(self):
        """Prune old records if the DB has grown."""
        try:
            with self._lock:
                cutoff = time.time() - (self.prune_days * 86400)
                self.conn.execute("DELETE FROM savings WHERE timestamp < ?", (cutoff,))
                self.conn.execute("DELETE FROM sessions WHERE last_seen < ?", (cutoff,))
                self.conn.commit()
        except sqlite3.Error:
            pass

    def record_saving(
        self, command: str, processor: str, original_size: int, compressed_size: int, platform: str
    ):
        """Record a single compression event."""
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO savings (timestamp, session_id, command, processor, "
                    "original_size, compressed_size, platform) VALUES (?, ?, ?, ?, ?, ?, ?)",
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

    def get_session_stats(self, session_id: str | None = None) -> dict:
        """Get stats for a session."""
        sid = session_id or self.session_id
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (sid,)
            ).fetchone()
        if not row:
            return {"commands": 0, "original": 0, "compressed": 0, "saved": 0, "ratio": 0.0}
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
        """Get aggregated stats across all sessions."""
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

    def get_top_processors(self, limit: int = 5) -> list[dict]:
        """Get the most effective processors."""
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
            {"processor": r["processor"], "count": r["count"], "saved": r["total_saved"]}
            for r in rows
        ]

    @staticmethod
    def _chars_to_tokens(n: int) -> int:
        """Estimate token count from character count."""
        from src import config  # noqa: PLC0415

        return max(1, round(n / config.get("chars_per_token"))) if n > 0 else 0

    @staticmethod
    def _format_tokens(n: int) -> str:
        """Human-readable token count."""
        if n < 1_000:
            return f"{n} tokens"
        if n < 1_000_000:
            return f"{n / 1_000:.1f}k tokens"
        return f"{n / 1_000_000:.1f}M tokens"

    def format_stats_message(self) -> str:
        """Format a human-readable stats summary."""
        lifetime = self.get_lifetime_stats()
        session = self.get_session_stats()

        parts = ["[token-saver]"]

        if lifetime["commands"] > 0:
            saved_tokens = self._chars_to_tokens(lifetime["saved"])
            parts.append(
                f"Lifetime: {lifetime['commands']} cmds, "
                f"{self._format_tokens(saved_tokens)} saved ({lifetime['ratio']}%)"
            )

        if session["commands"] > 0:
            saved_tokens = self._chars_to_tokens(session["saved"])
            parts.append(
                f"Session: {session['commands']} cmds, "
                f"{self._format_tokens(saved_tokens)} saved ({session['ratio']}%)"
            )

        if lifetime["commands"] == 0:
            parts.append("Ready. No compressions recorded yet.")

        return " | ".join(parts)

    def close(self):
        with self._lock, contextlib.suppress(sqlite3.Error):
            self.conn.close()
