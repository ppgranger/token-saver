"""Compression engine: orchestrates processors with configurable thresholds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import config
from .processors import discover_processors

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

    def compress(self, command: str, output: str) -> tuple[str, str, bool]:
        """Compress output for a given command.

        Returns (compressed_output, processor_name, was_compressed).
        """
        if not config.get("enabled"):
            return output, "none", False

        min_len = config.get("min_input_length")
        min_ratio = config.get("min_compression_ratio")

        if len(output) < min_len:
            return output, "none", False

        for processor in self.processors:
            if processor.can_handle(command):
                compressed = processor.process(command, output)

                # If the processor returned output exactly unchanged, it
                # explicitly chose not to compress (e.g. source code files).
                # Respect the processor's decision — no generic fallback.
                if compressed is output or compressed == output:
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
                        chained = secondary.process(command, compressed)
                        if chained is not compressed and chained != compressed:
                            compressed = chained
                        depth += 1

                # If a specialized processor handled it, also run generic
                # cleanup (ANSI strip, blank line collapse) but not truncation
                if processor is not self._generic:
                    compressed = self._generic.clean(compressed)

                original_len = len(output)
                compressed_len = len(compressed)
                gain = (original_len - compressed_len) / original_len if original_len > 0 else 0

                if compressed_len < original_len and gain >= min_ratio:
                    return compressed, processor.name, True

                # Specialized processor didn't compress enough — try the
                # generic processor as fallback (dedup, truncation, etc.)
                if processor is not self._generic:
                    generic_compressed = self._generic.process(command, output)
                    generic_compressed = self._generic.clean(generic_compressed)
                    generic_len = len(generic_compressed)
                    generic_gain = (
                        (original_len - generic_len) / original_len if original_len > 0 else 0
                    )
                    if generic_len < original_len and generic_gain >= min_ratio:
                        return generic_compressed, "generic", True

                return output, processor.name, False

        return output, "none", False
