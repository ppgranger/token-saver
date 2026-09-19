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

"""Shared compression core used by both the Claude and Antigravity hooks.

The core adapts a compression backend to the result consumed by both hosts.
Routing policy and optional telemetry have separate owners; the historical
recording functions remain available here for integration compatibility.
Importing or using compression alone does not initialize audit or tracking I/O.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from src import command_policy
from src import engine as engine_lib
from src import telemetry

if TYPE_CHECKING:
    from collections.abc import Mapping

_log = logging.getLogger("token-saver.core")
_log.addHandler(logging.NullHandler())

# Preserve the public recording entry points while keeping their disk and
# database lifecycle in the telemetry adapter.
# pylint: disable=invalid-name
audit_log = telemetry.audit_log
record_saving = telemetry.record_saving
record_mismatches = telemetry.record_mismatches
# pylint: enable=invalid-name


class Compressor(Protocol):
    """Compression and observation contract needed by platform integrations.

    Implementations never execute the command label. Metadata describes only
    the most recent call; it must not contain captured output or command text.
    """

    @property
    def last_event(self) -> Mapping[str, Any]:
        """Return the most recent routing, size, and redaction metadata."""

    def compress(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> tuple[str, str, bool]:
        """Return output, processor name, and whether the output changed."""


class CompressResult(NamedTuple):
    """Outcome of a single compression, independent of engine internals.

    Attributes:
        compressed: Output returned to the host integration.
        processor: Name of the processor supplying the final output.
        was_compressed: Whether output changed, including secret redaction.
        is_mismatch: Whether a specialized processor missed its size target.
        attempted_processor: Name of the originally selected processor.
        original_len: Original output length in characters.
        compressed_len: Returned output length in characters.
    """

    compressed: str
    processor: str
    was_compressed: bool
    is_mismatch: bool
    attempted_processor: str
    original_len: int
    compressed_len: int


def should_compress(command: str) -> bool:
    """Whether ``command`` is eligible for compression (shared gate).

    Delegates to the shared runtime policy so Claude and Antigravity make
    the same call without importing either platform adapter.

    Args:
        command: Shell command text associated with the captured output.

    Returns:
        Whether the shared hook eligibility rules allow compression.
    """
    return command_policy.is_compressible(command)


def compress(
    command: str,
    output: str,
    *,
    engine: Compressor | None = None,
    exit_code: int | None = None,
) -> CompressResult:
    """Compress captured output and fall back when a processor raises.

    An absent engine is constructed before compression. Engine initialization
    errors propagate; failures while compressing return the original output.

    Args:
        command: Shell command text associated with the captured output.
        output: Captured command output before compression.
        engine: Engine to reuse, or None to construct the default engine.
        exit_code: Original command exit status, or None when it is unknown.

    Returns:
        Compressed text and routing/size metadata, with passthrough on a
        processor error.
    """
    if engine is None:
        engine = engine_lib.CompressionEngine()
    try:
        compressed, processor_name, was_compressed = engine.compress(
            command, output, exit_code=exit_code
        )
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _log.warning("Compression failed; passing through captured output")
        compressed, processor_name, was_compressed = (
            output,
            "passthrough",
            False,
        )
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


def record_result(result: CompressResult, command: str, platform: str) -> None:
    """Audit-log, then record savings and/or mismatch from a CompressResult.

    Args:
        result: Compression outcome whose metadata should be recorded.
        command: Shell command text associated with the captured output.
        platform: Name of the host integration recording the event.
    """
    audit_log(
        command, result.processor, result.original_len, result.compressed_len
    )
    if result.is_mismatch:
        record_mismatches(
            [(command, result.attempted_processor, result.original_len)],
            platform,
        )
    if result.was_compressed:
        record_saving(
            command,
            result.processor,
            result.original_len,
            result.compressed_len,
            platform,
        )
