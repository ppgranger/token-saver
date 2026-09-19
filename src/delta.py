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

"""Compare sanitized diagnostics from actual command executions.

Delta never executes or caches commands. It is an opt-in presentation layer
for the Claude wrapper; ordinary compression and processor APIs stay stateless.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

import src
from src import chain_utils
from src import config
from src import delta_redaction
from src import delta_store
from src import diagnostics
from src import shell_syntax

if TYPE_CHECKING:
    from src import core
    from src import engine as engine_lib

_LOG = logging.getLogger(__name__)
_SCHEMA = 1


def restore(payload: dict) -> tuple[diagnostics.Snapshot, int]:
    """Validate a stored record before rendering or comparing its contents.

    Args:
        payload: Decoded, size-bounded record read from the private store.

    Returns:
        The structured snapshot and original command exit status.

    Raises:
        ValueError: The record has an unsupported schema or malformed fields.
    """
    schema = payload.get("schema")
    if (
        isinstance(schema, bool)
        or not isinstance(schema, int)
        or schema != _SCHEMA
    ):
        raise ValueError("unsupported Delta snapshot schema")
    exit_code = payload.get("exit_code")
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or exit_code not in (0, 1)
    ):
        raise ValueError("invalid Delta exit status")
    for key in ("family", "summary", "context"):
        if not isinstance(payload.get(key), str):
            raise ValueError("invalid Delta snapshot text")
    items = payload.get("diagnostics")
    passed = payload.get("passed")
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("invalid Delta diagnostic inventory")
    if (
        not isinstance(passed, list)
        or not all(isinstance(item, str) and item for item in passed)
        or len(set(passed)) != len(passed)
    ):
        raise ValueError("invalid Delta passed inventory")
    records = []
    seen = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"identifier", "summary", "detail"}
            or not all(isinstance(value, str) for value in item.values())
        ):
            raise ValueError("invalid Delta diagnostic")
        identifier = item["identifier"]
        if not identifier or identifier in seen or identifier in passed:
            raise ValueError("ambiguous Delta diagnostic identity")
        seen.add(identifier)
        records.append(diagnostics.Diagnostic(**item))
    snapshot = diagnostics.Snapshot(
        family=payload["family"],
        summary=payload["summary"],
        diagnostics=tuple(records),
        passed=tuple(passed),
        context=payload["context"],
    )
    return snapshot, exit_code


def render(
    snapshot: diagnostics.Snapshot,
    *,
    exit_code: int,
    previous: diagnostics.Snapshot | None = None,
    run_id: str = "",
) -> str:
    """Render current diagnostics, eliding only identical prior details.

    Every current failure stays named. A missing previous failure is only
    called passed if this run explicitly reported its successful result.
    Otherwise it is not observed, which never implies it was fixed. Each
    record stores full current details so reading it needs no prior context.

    Args:
        snapshot: Current sanitized parsed output.
        exit_code: Actual command exit status.
        previous: Comparable prior snapshot, or None for a complete baseline.
        run_id: Stored current record ID used for a detail-retrieval hint.

    Returns:
        A self-contained current state with full new or changed diagnostics.
    """
    return _render(
        snapshot,
        diagnostics.compare(snapshot, previous),
        exit_code=exit_code,
        run_id=run_id,
    )


def _render(
    snapshot: diagnostics.Snapshot,
    changes: tuple[diagnostics.Change, ...],
    *,
    exit_code: int,
    run_id: str = "",
) -> str:
    """Present already-classified observations without comparison policy."""
    lines = [
        f"[token-saver delta] {snapshot.family} | exit {exit_code}",
        snapshot.summary,
    ]
    for change in changes:
        item = change.diagnostic
        if change.status == "PASSED":
            summary = "explicitly passed this run"
        elif change.status == "NOT OBSERVED":
            summary = "not confirmed fixed"
        else:
            summary = item.summary
        lines.append(f"{change.status} {item.identifier} — {summary}")
        if change.needs_detail:
            lines.append(item.detail.rstrip("\r\n"))
    if snapshot.context.strip():
        lines.extend(["", snapshot.context.rstrip("\r\n")])
    if run_id:
        lines.extend(
            ["", f"Details: token-saver delta show {run_id} [--diagnostic ID]"]
        )
    return "\n".join(lines) + "\n"


def open_store() -> delta_store.Store:
    """Open the private store using trusted, bounded retention settings.

    Returns:
        A store to use as a context manager.

    Raises:
        OSError: The storage location cannot be accessed safely.
        ValueError: The configured retention limits are invalid.
        sqlite3.Error: The database cannot be opened or initialized.
    """
    return delta_store.Store(
        retention_hours=config.get("delta_retention_hours"),
        max_runs=config.get("delta_max_runs"),
    )


def _scope(command: str, session_id: str, family: str) -> str:
    identity = json.dumps(
        [
            _SCHEMA,
            src.__version__,
            session_id,
            os.path.realpath(os.getcwd()),
            command,
            family,
        ],
        ensure_ascii=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def apply(
    command: str,
    output: str,
    fallback: core.CompressResult,
    *,
    engine: engine_lib.CompressionEngine,
    exit_code: int,
    session_id: str,
) -> core.CompressResult:
    """Apply opt-in Delta after a single completed wrapper execution.

    Unsupported commands, unknown output and unavailable storage retain
    ordinary compression. Once sanitization has run, every fallback retains
    its masking. No output is stored unless a processor validates a snapshot.
    Chains, pipes, redirects and failed/incomplete process termination are
    excluded. Exceptions at this optional integration boundary are recorded
    without commands, captured output, exception text or tracebacks.

    Args:
        command: Exact executed command, used only to scope comparisons.
        output: Captured output before ordinary lossy compression.
        fallback: Existing compression result if Delta cannot be applied.
        engine: Active processor registry and settings.
        exit_code: Actual command exit status.
        session_id: Explicit host session identifier; empty disables Delta.

    Returns:
        Current diagnostics with retrievable details, or a safe fallback.
    """
    if (
        not config.get("enabled")
        or not config.get("delta_enabled")
        or not session_id
        # A processor can mask proprietary formats unknown to Delta. Its
        # sanitized result must never be replaced using the original input.
        or engine.last_event.get("redacted", False)
        or exit_code not in (0, 1)
        or len(output.encode("utf-8")) > 1_000_000
        or shell_syntax.has_unquoted(
            command, ("|", "&", ";", "\n", "<", ">", "$(", "`")
        )
    ):
        return fallback
    safe_fallback = fallback
    try:
        sanitized = delta_redaction.sanitize(output)
        if sanitized != output:
            # Core configures hook audit logging on import. Keep it out of
            # read-only CLI imports such as `version` and `--help`.
            # pylint: disable-next=import-outside-toplevel
            from src import core  # noqa: PLC0415

            safe_fallback = core.compress(
                chain_utils.extract_primary_command(command),
                sanitized,
                engine=engine,
                exit_code=exit_code,
            )._replace(original_len=len(output), was_compressed=True)
            if engine.last_event.get("redacted", False):
                return safe_fallback
        snapshot = engine.diagnostics(command, sanitized, exit_code=exit_code)
        if snapshot is None:
            return safe_fallback
        payload = dataclasses.asdict(snapshot)
        payload.update(schema=_SCHEMA, exit_code=exit_code)
        # Validate the same JSON representation used by the storage adapter.
        # This also protects the optional user-processor extension boundary.
        snapshot, _ = restore(json.loads(json.dumps(payload)))
        with open_store() as store:
            scope = _scope(command, session_id, snapshot.family)
            prior = store.latest(scope)
            previous = restore(prior[1])[0] if prior is not None else None
            run_id = store.save(scope, payload)
        changes = diagnostics.compare(snapshot, previous)
        rendered = _render(
            snapshot,
            changes,
            exit_code=exit_code,
            run_id=run_id,
        )
    # Optional processors and storage must not break the executed command.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _LOG.warning("Delta unavailable; retaining ordinary compression")
        return safe_fallback
    # A delta's headings may outweigh savings on short output. Ordinary
    # compression can win only if it still contains every new/changed detail:
    # the size gate must never reintroduce traceback truncation for those.
    retains_fresh = all(
        change.diagnostic.detail.rstrip("\r\n") in safe_fallback.compressed
        for change in changes
        if change.needs_detail
    )
    if len(rendered) >= len(safe_fallback.compressed) and retains_fresh:
        return safe_fallback
    return safe_fallback._replace(
        compressed=rendered,
        was_compressed=rendered != output,
        is_mismatch=False,
        original_len=len(output),
        compressed_len=len(rendered),
    )
