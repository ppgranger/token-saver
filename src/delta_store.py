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

"""Private, bounded storage for already redacted Delta snapshots.

The caller must redact payloads before passing them to this module. Scope
strings are hashed, and run identifiers contain no command or session data.
Expiry prevents retrieval and deletes records on the next store operation.
Records dated in the future after a clock rollback are also discarded rather
than extending their retention. Deletion does not promise secure erasure from
filesystem snapshots or backups.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from typing import Any

import src

MAX_PAYLOAD_BYTES = 1024 * 1024
_RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def _private_file(path: str) -> None:
    """Reject links and nonregular files before restricting file permissions."""
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("Unsafe Delta data file")
    os.chmod(path, 0o600)


def _prepare_database(directory: str) -> str:
    """Prepare a dedicated private directory and validate SQLite sidecars."""
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if not stat.S_ISDIR(os.lstat(directory).st_mode):
        raise ValueError("Unsafe Delta data directory")
    os.chmod(directory, 0o700)
    path = os.path.join(directory, "snapshots.sqlite3")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        _private_file(path)
    except PermissionError:
        # Windows reports EACCES, not EEXIST, for an existing directory.
        # Preserve genuine access failures for regular or missing files.
        if os.path.isdir(path):
            raise ValueError("Unsafe Delta data file") from None
        raise
    else:
        os.close(descriptor)
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = path + suffix
        try:
            _private_file(sidecar)
        except FileNotFoundError:
            # SQLite removes these optional files after completed transactions.
            # Another connection may remove one during metadata validation.
            continue
    return path


def _scope_key(scope: str) -> str:
    """Hash scope metadata so its original spelling never reaches storage."""
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


def _decode(payload: str) -> dict[str, Any]:
    """Validate stored JSON without silently replacing corrupt records."""
    if not isinstance(payload, str):
        raise ValueError("Invalid Delta snapshot")
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Delta snapshot exceeds the storage limit")
    try:
        result = json.loads(payload)
    except RecursionError:
        # Older supported Python decoders reject deeply nested JSON before
        # schema validation. Expose the same content-free validation failure.
        raise ValueError("Invalid Delta snapshot nesting") from None
    if not isinstance(result, dict):
        raise ValueError("Invalid Delta snapshot")
    return result


class Store:
    """Persist redacted snapshots independently from the savings database.

    Separate instances may write concurrently through SQLite transactions.
    An instance belongs to its creating thread. Directories and data files
    reject symlinks and have private POSIX permissions; on Windows, access
    also depends on the containing directory's ACL. The containing path must
    be trusted: this is not isolation from another process of the same user.
    Storage errors propagate so the caller can return ordinary output.
    """

    def __init__(
        self,
        directory: str | None = None,
        *,
        retention_hours: int = 24,
        max_runs: int = 100,
    ) -> None:
        """Open a dedicated Delta database without recovering corrupt data.

        Args:
            directory: Dedicated directory, or None for a ``delta`` directory
                below TOKEN_SAVER_DB_DIR or the platform's data directory.
            retention_hours: Lifetime of each snapshot, from 1 to 168 hours.
            max_runs: Global snapshot maximum, from 1 to 1000.

        Raises:
            ValueError: Bounds are invalid or a data path is unsafe.
            OSError: The private directory or database cannot be prepared.
            sqlite3.Error: Database content or schema cannot be used.
        """
        for value, maximum in ((retention_hours, 168), (max_runs, 1000)):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= maximum
            ):
                raise ValueError("Delta storage bound is outside its range")
        self._retention_seconds = retention_hours * 3600
        self._max_runs = max_runs
        if directory is None:
            base = os.environ.get("TOKEN_SAVER_DB_DIR") or src.data_dir()
            directory = os.path.join(base, "delta")
        path = _prepare_database(directory)
        self._connection = sqlite3.connect(path, timeout=5)
        try:
            self._connection.execute("PRAGMA secure_delete = ON")
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                self._initialize()
                self._prune()
        except (sqlite3.Error, ValueError):
            self._connection.close()
            raise

    def _initialize(self) -> None:
        """Create the versioned schema only in an empty SQLite database."""
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            existing = self._connection.execute(
                "SELECT name FROM sqlite_master LIMIT 1"
            ).fetchone()
            if existing is not None:
                raise ValueError("Unrecognized Delta database schema")
            self._connection.execute(
                "CREATE TABLE snapshots ("
                "run_id TEXT PRIMARY KEY, scope TEXT NOT NULL, "
                "created REAL NOT NULL, payload TEXT NOT NULL)"
            )
            self._connection.execute("PRAGMA user_version = 1")
        elif version != 1:
            raise ValueError("Unsupported Delta database version")
        # Access each expected column even when there are no records.
        self._connection.execute(
            "SELECT run_id, scope, created, payload FROM snapshots LIMIT 0"
        )

    def _prune(self, now: float | None = None) -> None:
        """Prune expired/future records and keep the newest inserted runs.

        A wall-clock rollback invalidates future-dated records so it cannot
        extend their lifetime or displace a newly committed snapshot. Saving
        supplies the same timestamp used by its insert for a consistent bound.
        """
        if now is None:
            now = time.time()
        self._connection.execute(
            "DELETE FROM snapshots WHERE created <= ? OR created > ?",
            (now - self._retention_seconds, now),
        )
        self._connection.execute(
            "DELETE FROM snapshots WHERE rowid NOT IN ("
            "SELECT rowid FROM snapshots ORDER BY rowid DESC LIMIT ?)",
            (self._max_runs,),
        )

    def save(self, scope: str, payload: dict[str, Any]) -> str:
        """Atomically save an already sanitized snapshot and enforce limits.

        Args:
            scope: Comparison context; only its SHA-256 digest is persisted.
            payload: JSON object sanitized by the caller before this boundary.

        Returns:
            Opaque lowercase hexadecimal run identifier.

        Raises:
            ValueError: Payload is not an object, is invalid, or exceeds 1 MiB.
            TypeError: Payload includes values unsupported by JSON.
            sqlite3.Error: The transaction cannot be committed.
        """
        if not isinstance(payload, dict):
            raise ValueError("Delta snapshot must be a JSON object")
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(serialized.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("Delta snapshot exceeds the storage limit")
        run_id = uuid.uuid4().hex
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            now = time.time()
            self._connection.execute(
                "INSERT INTO snapshots (run_id, scope, created, payload) "
                "VALUES (?, ?, ?, ?)",
                (run_id, _scope_key(scope), now, serialized),
            )
            self._prune(now)
        return run_id

    def latest(self, scope: str) -> tuple[str, dict[str, Any]] | None:
        """Return the last inserted unexpired snapshot for exactly one scope.

        Args:
            scope: Comparison context used when saving snapshots.

        Returns:
            Run identifier and JSON object, or None when no snapshot remains.

        Raises:
            ValueError: A stored snapshot is invalid.
            sqlite3.Error: The database cannot be read or pruned.
        """
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._prune()
            row = self._connection.execute(
                "SELECT run_id, payload FROM snapshots WHERE scope = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (_scope_key(scope),),
            ).fetchone()
        return (row[0], _decode(row[1])) if row is not None else None

    def get(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve an unexpired snapshot using its opaque identifier.

        Args:
            run_id: Exactly 32 lowercase hexadecimal characters.

        Returns:
            The stored JSON object, or None if it has expired or is unknown.

        Raises:
            ValueError: Identifier or stored snapshot is invalid.
            sqlite3.Error: The database cannot be read or pruned.
        """
        if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("Invalid Delta run identifier")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._prune()
            row = self._connection.execute(
                "SELECT payload FROM snapshots WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _decode(row[0]) if row is not None else None

    def clear(self) -> int:
        """Delete all snapshots, returning the number of removed records.

        Returns:
            Count of deleted snapshots, including any not yet pruned by age.

        Raises:
            sqlite3.Error: The deletion cannot be committed.
        """
        with self._connection:
            deleted = self._connection.execute("DELETE FROM snapshots")
        return deleted.rowcount

    def close(self) -> None:
        """Release the SQLite connection; repeated closes are safe."""
        self._connection.close()

    def __enter__(self) -> Store:
        """Return this open store for deterministic connection cleanup."""
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the store without suppressing errors from the caller."""
        self.close()
