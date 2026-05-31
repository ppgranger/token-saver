"""Shared compression core used by both the Claude and Antigravity hooks.

The two platforms integrate differently — Claude rewrites the Bash command to
run through ``wrap.py`` (PreToolUse), while Antigravity compresses already-captured
tool output (AfterTool) — but the *decision* of what to compress and the
*bookkeeping* afterwards (audit log, savings, mismatch events) are identical.
This module centralizes both so the two entry points stay in lock-step.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import NamedTuple

from .engine import CompressionEngine
from .tracker import SavingsTracker

_log = logging.getLogger("token-saver.core")
_log.addHandler(logging.NullHandler())

# Always-on audit log (records processor + ratio, never output content), so
# "why did this route to generic?" is answerable after the fact.  Rotated to
# stay bounded; failures are non-fatal.
_audit = logging.getLogger("token-saver.audit")
_audit.setLevel(logging.INFO)
if not _audit.handlers:
    try:
        from . import data_dir

        _adir = data_dir()
        os.makedirs(_adir, exist_ok=True)
        _audit_handler = RotatingFileHandler(
            os.path.join(_adir, "audit.log"), maxBytes=1_000_000, backupCount=1
        )
        _audit_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _audit.addHandler(_audit_handler)
    except Exception:
        _audit.addHandler(logging.NullHandler())


class CompressResult(NamedTuple):
    """Outcome of a single compression, decoupled from the engine internals."""

    compressed: str
    processor: str
    was_compressed: bool
    is_mismatch: bool
    attempted_processor: str
    original_len: int
    compressed_len: int


def should_compress(command: str) -> bool:
    """Whether ``command`` is eligible for compression (shared gate).

    Delegates to the PreToolUse decision logic so Claude and Antigravity make the
    same call.  Imported lazily to avoid a src->scripts import at module load.
    """
    from scripts.hook_pretool import is_compressible  # noqa: PLC0415

    return is_compressible(command)


def compress(
    command: str, output: str, *, engine: CompressionEngine | None = None
) -> CompressResult:
    """Compress ``output`` for ``command``; never raises (passes through on error)."""
    engine = engine or CompressionEngine()
    try:
        compressed, processor_name, was_compressed = engine.compress(command, output)
    except Exception:
        _log.exception("Compression failed for %r — passing through", command)
        compressed, processor_name, was_compressed = output, "passthrough", False
    ev = engine.last_event or {}
    return CompressResult(
        compressed=compressed,
        processor=processor_name,
        was_compressed=was_compressed,
        is_mismatch=bool(ev.get("is_mismatch")),
        attempted_processor=ev.get("attempted_processor", processor_name),
        original_len=len(output),
        compressed_len=len(compressed),
    )


def audit_log(command: str, processor: str, original_len: int, compressed_len: int) -> None:
    """Append a single audit line (no output content) — best effort."""
    try:
        ratio = ((original_len - compressed_len) / original_len * 100) if original_len > 0 else 0.0
        _audit.info(
            "processor=%s original=%d compressed=%d ratio=%.1f%% cmd=%r",
            processor,
            original_len,
            compressed_len,
            ratio,
            command[:120],
        )
    except Exception:
        _log.debug("Audit logging failed", exc_info=True)


def record_saving(
    command: str, processor: str, original_len: int, compressed_len: int, platform: str
) -> None:
    """Record a savings row — best effort."""
    try:
        tracker = SavingsTracker()
        tracker.record_saving(
            command=command,
            processor=processor,
            original_size=original_len,
            compressed_size=compressed_len,
            platform=platform,
        )
        tracker.close()
    except Exception:
        _log.exception("Tracking failed")


def record_mismatches(items: list[tuple[str, str, int]], platform: str) -> None:
    """Record processor-mismatch events in one tracker session — best effort.

    Each item is (command, attempted_processor, original_len).
    """
    if not items:
        return
    try:
        tracker = SavingsTracker()
        for command, processor, original_len in items:
            tracker.record_mismatch(
                command=command,
                processor=processor,
                original_size=original_len,
                platform=platform,
            )
        tracker.close()
    except Exception:
        _log.exception("Mismatch tracking failed")


def record_result(result: CompressResult, command: str, platform: str) -> None:
    """Audit-log, then record savings and/or mismatch from a CompressResult."""
    audit_log(command, result.processor, result.original_len, result.compressed_len)
    if result.is_mismatch:
        record_mismatches([(command, result.attempted_processor, result.original_len)], platform)
    if result.was_compressed:
        record_saving(
            command, result.processor, result.original_len, result.compressed_len, platform
        )
