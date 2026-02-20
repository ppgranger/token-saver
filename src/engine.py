"""Compression engine: orchestrates processors with configurable thresholds."""

from . import config
from .processors import discover_processors


class CompressionEngine:
    """Iterates processors in priority order; first match wins.

    After the specialized processor runs, GenericProcessor is applied as a
    second pass to clean up ANSI codes, dedup remaining repetitions, etc.
    """

    def __init__(self):
        self.processors = discover_processors()
        self._generic = self.processors[-1]  # Last = GenericProcessor (priority 999)

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

                # If a specialized processor handled it, also run generic
                # cleanup (ANSI strip, blank line collapse) but not truncation
                if processor is not self._generic:
                    compressed = self._generic.clean(compressed)

                original_len = len(output)
                compressed_len = len(compressed)
                gain = (original_len - compressed_len) / original_len if original_len > 0 else 0

                if gain >= min_ratio:
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
                    if generic_gain >= min_ratio:
                        return generic_compressed, "generic", True

                return output, processor.name, False

        return output, "none", False
