"""Compression engine: orchestrates processors with configurable thresholds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import config
from .processors import discover_processors
from .processors.critical import missing_critical

if TYPE_CHECKING:
    from .processors.base import Processor


class CompressionEngine:
    """Iterates processors in priority order; first match wins.

    After the specialized processor runs, GenericProcessor is applied as a
    second pass to clean up ANSI codes, dedup remaining repetitions, etc.
    """

    processors: list[Processor]
    _generic: Processor
    _by_name: dict[str, Processor]

    def __init__(self) -> None:
        all_processors = discover_processors()
        raw_disabled = config.get("disabled_processors") or []
        disabled = set(raw_disabled if isinstance(raw_disabled, list) else [])
        # Never disable generic — it's the fallback and provides clean()
        disabled.discard("generic")
        self.processors = [p for p in all_processors if p.name not in disabled]
        self._generic = self.processors[-1]  # Last = GenericProcessor (priority 999)
        self._by_name = {p.name: p for p in self.processors}
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

    def _select(self, command: str, exit_code: int | None) -> Processor | None:
        """Return the processor that should handle ``command``, if any.

        When the command failed, a processor that has not opted into
        ``handles_failure`` is skipped in favour of GenericProcessor: the error
        text is usually in a shape the specialized processor doesn't recognize,
        and dropping unrecognized lines is exactly how a failure reason gets
        lost.  Generic truncates with an explicit marker instead.
        """
        failed = exit_code is not None and exit_code != 0
        for processor in self.processors:
            if not processor.can_handle(command):
                continue
            if failed and not processor.handles_failure and processor is not self._generic:
                return self._generic
            return processor
        return None

    def _call_process(
        self, processor: Processor, command: str, output: str, exit_code: int | None
    ) -> str:
        """Call ``processor.process()``, passing ``exit_code`` only if it wants it.

        Every processor accepts ``(command, output)``; only the handful that
        set ``wants_exit_code = True`` also accept the ``exit_code`` keyword.
        Calling with it unconditionally would be a ``TypeError`` for the other
        ~35 processors.
        """
        if processor.wants_exit_code:
            # Processors that opt in via wants_exit_code declare a wider
            # signature than the base class's abstract `process()` — mypy
            # only sees the base signature here, hence the ignore.
            return processor.process(command, output, exit_code=exit_code)  # type: ignore[call-arg]
        return processor.process(command, output)

    def _recover_critical(self, original: str, compressed: str, processor: Processor) -> str:
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
        """
        if processor.handles_failure:
            return compressed
        cap = config.get("recover_critical_lines")
        if not cap or cap <= 0:
            return compressed
        missing = missing_critical(original, compressed)
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

        Returns (compressed_output, processor_name, was_compressed).
        """
        self.last_event = {}
        if not config.get("enabled"):
            return output, "none", False

        min_len = config.get("min_input_length")
        min_ratio = config.get("min_compression_ratio")

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

        # Chain to secondary processors if declared
        chain_list = processor.chain_to
        if chain_list:
            if isinstance(chain_list, str):
                chain_list = [chain_list]
            max_depth = config.get("max_chain_depth")
            visited = {processor.name}
            depth = 0
            for chain_name in chain_list:
                if depth >= max_depth:
                    break
                if chain_name in visited or chain_name not in self._by_name:
                    continue
                secondary = self._by_name[chain_name]
                visited.add(chain_name)
                chained = self._call_process(secondary, command, compressed, exit_code)
                if chained is not compressed and chained != compressed:
                    compressed = chained
                depth += 1

        # If a specialized processor handled it, also run generic
        # cleanup (ANSI strip, blank line collapse) but not truncation
        if processor is not self._generic:
            compressed = self._generic.clean(compressed)

        compressed = self._recover_critical(output, compressed, processor)

        # A processor that redacted secrets into `compressed` must never be
        # undone by a fallback that reintroduces `output` (the raw,
        # unredacted text) — whether that's this function returning `output`
        # directly below, or the mismatch path re-running generic on
        # `output` instead of on the already-redacted `compressed`.  Once
        # this is true, `output` is radioactive for the rest of this call.
        redacted = processor.redacted_secrets(command, output)

        original_len = len(output)
        compressed_len = len(compressed)
        gain = (original_len - compressed_len) / original_len if original_len > 0 else 0

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
            return compressed, processor.name, True

        # Specialized processor didn't compress enough on its own — a
        # mismatch (O3): record it and try the generic processor as a
        # fallback (dedup, truncation, etc.).  Not reached when `redacted`,
        # per the guard above — so there is no risk of generic seeing
        # unredacted `output` here.
        mismatch = processor is not self._generic
        if processor is not self._generic:
            generic_compressed = self._call_process(self._generic, command, output, exit_code)
            generic_compressed = self._generic.clean(generic_compressed)
            generic_compressed = self._recover_critical(output, generic_compressed, self._generic)
            generic_len = len(generic_compressed)
            generic_gain = (original_len - generic_len) / original_len if original_len > 0 else 0
            if generic_len < original_len and generic_gain >= min_ratio:
                self._set_event(
                    processor.name,
                    "generic",
                    True,
                    mismatch,
                    original_len,
                    generic_len,
                    failure_fallback,
                )
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
