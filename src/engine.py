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

"""Compression engine: orchestrates processors with configurable thresholds."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from src import config
from src import processors as processor_discovery
from src import registry
from src.processors import critical

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src import diagnostics as diagnostics_lib
    from src.processors import base

_LOGGER = logging.getLogger(__name__)


class EngineSettings(Protocol):
    """Read engine thresholds from configuration or an injected mapping."""

    def get(self, key: str) -> Any:
        """Return the configured value for an engine setting.

        Args:
            key: Engine configuration key to read.

        Returns:
            The corresponding configuration value.
        """


class CompressionEngine:
    """Iterates processors in priority order; first match wins.

    After the specialized processor runs, GenericProcessor is applied as a
    second pass to clean up ANSI codes, dedup remaining repetitions, etc.

    ``processors`` and ``settings`` are optional dependencies. Explicit
    processors bypass plugin discovery; settings control engine policy while
    individual processors retain their own configuration. The default reader
    remains live, so configuration reloads affect subsequent compressions.

    Attributes:
        processors: Enabled processor instances in routing priority order.
        last_event: Content-free metadata about the most recent compression,
            including the attempted and resulting processors and size changes.
            A true ``redacted`` flag forbids later adapters from reparsing the
            original output, whose secrets may use extension-specific formats.
    """

    processors: list[base.Processor]
    _generic: base.Processor
    _by_name: dict[str, base.Processor]

    def __init__(
        self,
        processors: Iterable[base.Processor] | None = None,
        *,
        settings: EngineSettings | None = None,
    ) -> None:
        """Create a routing engine with optional injected dependencies.

        Args:
            processors: Explicit instances, or None to discover installed and
                user-provided processors.
            settings: Configuration reader, or None for live global settings.

        Raises:
            ValueError: The processor collection lacks a valid generic fallback.
        """
        self._settings: EngineSettings = (
            config if settings is None else settings
        )
        all_processors = (
            processor_discovery.discover_processors()
            if processors is None
            else processors
        )
        raw_disabled = self._settings.get("disabled_processors") or []
        processor_registry = registry.ProcessorRegistry(
            all_processors,
            disabled=raw_disabled if isinstance(raw_disabled, list) else [],
        )
        self.processors = processor_registry.processors
        self._generic = processor_registry.generic
        self._by_name = processor_registry.by_name
        # Metadata about the most recent compress() call, for observability
        # (O3 processor-mismatch detection). Reset on every call.
        self.last_event: dict = {}

    def _set_event(
        self,
        attempted: str,
        result: str,
        was_compressed: bool,
        is_mismatch: bool,
        original_len: int,
        compressed_len: int,
        failure_fallback: bool = False,
    ) -> None:
        self.last_event = {
            "attempted_processor": attempted,
            "result_processor": result,
            "was_compressed": was_compressed,
            "is_mismatch": is_mismatch,
            "original_len": original_len,
            "compressed_len": compressed_len,
            "failure_fallback": failure_fallback,
        }

    def _select(
        self, command: str, exit_code: int | None
    ) -> base.Processor | None:
        """Return the processor that should handle ``command``, if any.

        When the command failed, a processor that has not opted into
        ``handles_failure`` is skipped in favour of GenericProcessor: the error
        text is usually in a shape the specialized processor doesn't recognize,
        and dropping unrecognized lines is exactly how a failure reason gets
        lost.  Generic truncates with an explicit marker instead.

        Args:
            command: Command label used by processor routing predicates.
            exit_code: Captured exit status, or None when unknown.

        Returns:
            The first matching processor, its safe failure fallback, or None.
        """
        failed = exit_code is not None and exit_code != 0
        for processor in self.processors:
            if not processor.can_handle(command):
                continue
            if (
                failed
                and not processor.handles_failure
                and processor is not self._generic
            ):
                return self._generic
            return processor
        return None

    def diagnostics(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> diagnostics_lib.Snapshot | None:
        """Extract optional structured diagnostics through the active processor.

        This does not persist output or change ordinary compression behavior.
        Callers storing diagnostics must sanitize the input first. Unsupported
        or ambiguous formats return None; extension failures propagate to the
        integration's isolation boundary.

        Args:
            command: Original command label; never executed here.
            output: Captured, sanitized output before lossy compression.
            exit_code: Captured exit status, or None when unavailable.

        Returns:
            A conservative snapshot, or None when diagnostics are unavailable.
        """
        if not self._settings.get("enabled"):
            return None
        processor = self._select(command, exit_code)
        if processor is None:
            return None
        return processor.diagnostics(command, output, exit_code=exit_code)

    def _call_process(
        self,
        processor: base.Processor,
        command: str,
        output: str,
        exit_code: int | None,
    ) -> str:
        """Call process(), forwarding exit_code only when the processor opts in.

        Every processor accepts ``(command, output)``; only the handful that
        set ``wants_exit_code = True`` also accept the ``exit_code`` keyword.
        Calling with it unconditionally would raise ``TypeError`` for
        processors that implement only the base contract.

        Args:
            processor: Processor instance to invoke.
            command: Command label for routing and contextual parsing.
            output: Captured output to transform.
            exit_code: Captured exit status, forwarded only when requested.

        Returns:
            The processor's transformed output.

        Raises:
            TypeError: An extension violates the text-output contract.
        """
        if processor.wants_exit_code:
            # Processors that opt in via wants_exit_code declare a wider
            # signature than the base class's abstract `process()` — mypy
            # only sees the base signature here, hence the ignore.
            result = processor.process(
                command,
                output,
                exit_code=exit_code,  # type: ignore[call-arg]
            )
        else:
            result = processor.process(command, output)
        if not isinstance(result, str):
            raise TypeError("Processor output must be text")
        return result

    def _clean_output(self, output: str, *, redacted: bool) -> str:
        """Apply optional cleanup while retaining the last safe text result.

        Args:
            output: Text returned by a completed processing pass.
            redacted: Whether any completed pass removed sensitive content.

        Returns:
            Cleaned text, or the supplied redacted text if cleanup fails.

        Raises:
            Exception: Cleanup failed before any successful redaction.
        """
        try:
            cleaned = self._generic.clean(output)
            if not isinstance(cleaned, str):
                raise TypeError("Processor cleanup must return text")
            return cleaned
        # Cleanup is an extension boundary. Neither exceptions nor invalid
        # return values may replace the last successfully redacted string.
        except Exception:  # pylint: disable=broad-exception-caught
            if not redacted:
                raise
            _LOGGER.warning(
                "Processor cleanup failed; retaining redacted output"
            )
            return output

    def _recover_critical(
        self, original: str, compressed: str, processor: base.Processor
    ) -> str:
        """Re-append error lines a processor dropped, so none are lost silently.

        Most processors are heuristics over a human-readable format they may
        not recognize, and the common failure mode is a loop with no ``else``
        branch: unmatched lines vanish with no marker and no counter.  Rather
        than audit 36 processors — and every future one — this is the single
        place that enforces the promise.

        Processors that set ``handles_failure`` are exempt.  Summarizing many
        errors into one grouped line ("20 issues across 2 rules") is precisely
        what makes a linter or test-runner processor valuable; re-appending the
        raw lines would undo the compression entirely.  Those processors are
        instead held to the promise directly, by
        ``TestFailureHandling::test_handles_failure_claim_is_earned``.

        The recovered block is capped (``recover_critical_lines``, 0 disables)
        so a wall of errors can't undo the compression, and lines already
        present in the compressed output are not repeated.

        Args:
            original: Input before compression; callers must exclude redactions.
            compressed: Candidate compressed output.
            processor: Processor whose failure-handling declaration applies.

        Returns:
            Output with missing critical lines restored up to the configured
            limit, or unchanged output when recovery does not apply.
        """
        if processor.handles_failure:
            return compressed
        cap = self._settings.get("recover_critical_lines")
        if not cap or cap <= 0:
            return compressed
        missing = critical.missing_critical(original, compressed)
        if not missing:
            return compressed
        kept = missing[:cap]
        note = f"[token-saver] {len(kept)} error line(s) recovered"
        if len(missing) > cap:
            note += f" ({len(missing) - cap} more omitted)"
        return "\n".join([compressed, note, *kept])

    def compress(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> tuple[str, str, bool]:
        """Compress output for a given command.

        ``exit_code`` is the command's exit status when known (``None`` when
        the caller has no way to know, e.g. Antigravity's captured output).  A
        non-zero value routes to GenericProcessor unless the matched processor
        sets ``handles_failure``.

        Args:
            command: Command label used to select a processor; never executed.
            output: Captured command output.
            exit_code: Captured command status, or None when unknown.

        Returns:
            A tuple of resulting output, processor name, and whether a changed
            result was accepted. Policy fallbacks preserve prior redactions.
        """
        self.last_event = {}
        if not self._settings.get("enabled"):
            return output, "none", False

        min_len = self._settings.get("min_input_length")
        min_ratio = self._settings.get("min_compression_ratio")

        if len(output) < min_len:
            return output, "none", False

        processor = self._select(command, exit_code)
        if processor is None:
            return output, "none", False

        # True when a specialized processor was bypassed because the command
        # failed — surfaced in last_event so `token-saver stats` can show it.
        failure_fallback = bool(exit_code) and processor is self._generic

        compressed = self._call_process(processor, command, output, exit_code)

        # If the processor returned output exactly unchanged, it
        # explicitly chose not to compress (e.g. source code files).
        # A deliberate no-op, not a weak-processor mismatch.
        if compressed is output or compressed == output:
            self._set_event(
                processor.name,
                processor.name,
                False,
                False,
                len(output),
                len(output),
                failure_fallback,
            )
            return output, processor.name, False

        # Track redaction before cleanup or chaining can change the input used
        # by the processor's predicate. Once any pass redacts, no later safety
        # or ratio fallback may reintroduce the original, unredacted text.
        redacted = processor.redacted_secrets(command, output)

        # Chain to secondary processors if declared
        chain_list = processor.chain_to
        if chain_list:
            if isinstance(chain_list, str):
                chain_list = [chain_list]
            max_depth = self._settings.get("max_chain_depth")
            visited = {processor.name}
            depth = 0
            for chain_name in chain_list:
                if depth >= max_depth:
                    break
                if chain_name in visited or chain_name not in self._by_name:
                    continue
                secondary = self._by_name[chain_name]
                visited.add(chain_name)
                secondary_redacts = redacted or secondary.redacted_secrets(
                    command, compressed
                )
                try:
                    chained = self._call_process(
                        secondary, command, compressed, exit_code
                    )
                # Plugins are an isolation boundary; preserve prior redactions
                # even if a user processor fails with an unexpected exception.
                except Exception:  # pylint: disable=broad-exception-caught
                    if not redacted:
                        raise
                    _LOGGER.warning(
                        "Processor chaining failed; retaining redacted output"
                    )
                    # core.compress() falls back to raw input on an engine
                    # exception. Keep the last safely redacted result instead.
                    break
                redacted = secondary_redacts
                if chained is not compressed and chained != compressed:
                    compressed = chained
                depth += 1

        # If a specialized processor handled it, also run generic
        # cleanup (ANSI strip, blank line collapse) but not truncation
        if processor is not self._generic:
            compressed = self._clean_output(compressed, redacted=redacted)

        # Critical-looking lines may themselves contain the secrets that were
        # just removed (e.g. API_KEY=error-secret). The engine has no generic
        # way to sanitize those raw lines, so redaction takes precedence over
        # recovery. Reprocessing a chained result could apply the wrong parser.
        if not redacted:
            compressed = self._recover_critical(output, compressed, processor)

        # A pass that redacted secrets into `compressed` must never be undone
        # by a fallback that reintroduces `output` (the raw,
        # unredacted text) — whether that's this function returning `output`
        # directly below, or the mismatch path re-running generic on
        # `output` instead of on the already-redacted `compressed`.  Once
        # this is true, `output` is radioactive for the rest of this call.
        original_len = len(output)
        compressed_len = len(compressed)
        gain = (
            (original_len - compressed_len) / original_len
            if original_len > 0
            else 0
        )

        if redacted or (compressed_len < original_len and gain >= min_ratio):
            self._set_event(
                processor.name,
                processor.name,
                True,
                False,
                original_len,
                compressed_len,
                failure_fallback,
            )
            self.last_event["redacted"] = redacted
            return compressed, processor.name, True

        # Specialized processor didn't compress enough on its own — a
        # mismatch (O3): record it and try the generic processor as a
        # fallback (dedup, truncation, etc.).  Not reached when `redacted`,
        # per the guard above — so there is no risk of generic seeing
        # unredacted `output` here.
        mismatch = processor is not self._generic
        if processor is not self._generic:
            generic_compressed = self._call_process(
                self._generic, command, output, exit_code
            )
            generic_redacted = self._generic.redacted_secrets(command, output)
            generic_compressed = self._clean_output(
                generic_compressed, redacted=generic_redacted
            )
            if not generic_redacted:
                generic_compressed = self._recover_critical(
                    output, generic_compressed, self._generic
                )
            generic_len = len(generic_compressed)
            generic_gain = (
                (original_len - generic_len) / original_len
                if original_len > 0
                else 0
            )
            if generic_redacted or (
                generic_len < original_len and generic_gain >= min_ratio
            ):
                self._set_event(
                    processor.name,
                    "generic",
                    True,
                    mismatch,
                    original_len,
                    generic_len,
                    failure_fallback,
                )
                self.last_event["redacted"] = generic_redacted
                return generic_compressed, "generic", True

        self._set_event(
            processor.name,
            processor.name,
            False,
            mismatch,
            original_len,
            compressed_len,
            failure_fallback,
        )
        return output, processor.name, False
