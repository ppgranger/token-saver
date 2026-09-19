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

"""Best-effort audit and savings adapters, separate from compression policy.

Importing this module creates no data directories, files, or SQLite connections.
Each recording call owns and closes its writer, including when recording fails.
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import os
import threading
from typing import TYPE_CHECKING, Protocol

import src
from src import tracker as tracker_lib

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)
_AUDIT = logging.getLogger("token-saver.audit")
_AUDIT_LOCK = threading.Lock()


class SavingsWriter(Protocol):
    """Write-only tracking operations needed by integration telemetry.

    Readers, schema management, and presentation are not part of this contract.
    The caller closes every writer returned by its factory, even after failures.
    """

    def record_saving(
        self,
        command: str,
        processor: str,
        original_size: int,
        compressed_size: int,
        platform: str,
    ) -> None:
        """Persist a savings observation; sizes are measured in characters."""

    def record_mismatch(
        self, command: str, processor: str, original_size: int, platform: str
    ) -> None:
        """Persist a processor mismatch without captured output."""

    def close(self) -> None:
        """Release the writer's resources, including after a failed write."""


class _AuditHandler(logging.handlers.RotatingFileHandler):
    """Keep optional write/rotation failures from revealing audit records."""

    def handleError(self, record: logging.LogRecord) -> None:
        """Report failure without logging's default record/traceback dump."""
        del record
        _LOGGER.warning("Audit logging failed")


def _get_audit_logger() -> logging.Logger:
    """Configure the rotating UTF-8 journal on first use.

    Existing host-supplied handlers take precedence. Initialization errors
    propagate to audit_log's best-effort boundary, allowing a later retry.
    """
    with _AUDIT_LOCK:
        if not _AUDIT.handlers:
            directory = src.data_dir()
            os.makedirs(directory, exist_ok=True)
            handler = _AuditHandler(
                os.path.join(directory, "audit.log"),
                maxBytes=1_000_000,
                backupCount=1,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            _AUDIT.addHandler(handler)
        _AUDIT.setLevel(logging.INFO)
    return _AUDIT


def audit_log(
    command: str, processor: str, original_len: int, compressed_len: int
) -> None:
    """Append a single audit line (no output content) — best effort.

    Args:
        command: Shell command text associated with the captured output.
        processor: Stable name of the processor that handled the output.
        original_len: Original output length in characters.
        compressed_len: Compressed output length in characters.
    """
    try:
        ratio = (
            ((original_len - compressed_len) / original_len * 100)
            if original_len > 0
            else 0.0
        )
        _get_audit_logger().info(
            "processor=%s original=%d compressed=%d ratio=%.1f%% cmd=%r",
            processor,
            original_len,
            compressed_len,
            ratio,
            command[:120],
        )
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _LOGGER.warning("Audit logging failed")


def record_saving(
    command: str,
    processor: str,
    original_len: int,
    compressed_len: int,
    platform: str,
    *,
    tracker_factory: Callable[[], SavingsWriter] | None = None,
) -> None:
    """Record a savings row — best effort.

    Args:
        command: Shell command text associated with the captured output.
        processor: Stable name of the processor that handled the output.
        original_len: Original output length in characters.
        compressed_len: Compressed output length in characters.
        platform: Name of the host integration recording the event.
        tracker_factory: Create a writer, or None for the default SQLite
            adapter.
    """
    try:
        factory = (
            tracker_lib.SavingsTracker
            if tracker_factory is None
            else tracker_factory
        )
        with contextlib.closing(factory()) as tracker:
            tracker.record_saving(
                command=command,
                processor=processor,
                original_size=original_len,
                compressed_size=compressed_len,
                platform=platform,
            )
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _LOGGER.warning("Tracking failed")


def record_mismatches(
    items: list[tuple[str, str, int]],
    platform: str,
    *,
    tracker_factory: Callable[[], SavingsWriter] | None = None,
) -> None:
    """Record processor-mismatch events in one tracker session — best effort.

    Each item is (command, attempted_processor, original_len).

    Args:
        items: Command, attempted processor, and original character-count
            tuples.
        platform: Name of the host integration recording the event.
        tracker_factory: Create a writer, or None for the default SQLite
            adapter.
    """
    if not items:
        return
    try:
        factory = (
            tracker_lib.SavingsTracker
            if tracker_factory is None
            else tracker_factory
        )
        with contextlib.closing(factory()) as tracker:
            for command, processor, original_len in items:
                tracker.record_mismatch(
                    command=command,
                    processor=processor,
                    original_size=original_len,
                    platform=platform,
                )
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _LOGGER.warning("Mismatch tracking failed")
