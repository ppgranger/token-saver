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

"""Abstract base class for output processors."""

import abc

from src import diagnostics

# Matches any Python invocation: python, python3, python3.11,
# .venv/bin/python3, /usr/bin/python, C:/Python/python.exe, etc.
PYTHON_CMD = r"(?:\S+/)?python[23]?(?:\.\d+)?(?:\.exe)?"


class Processor(abc.ABC):
    """Base class for all output processors.

    Subclasses must set ``priority`` and ``hook_patterns`` as class-level
    attributes so the registry can auto-discover, order, and collect patterns.

    Priority conventions:
        10-19  High priority overrides (e.g. PackageListProcessor before build)
        20-29  Core processors (git, test, build, lint)
        30-49  Specialized command families (network, containers, system tools)
        50-69  Content-based (file_listing, file_content)
        999    Generic fallback (must always be last)

    Attributes:
        priority: Routing order; lower numbers run first.
        hook_patterns: Anchored command patterns exposed to platform hooks.
        chain_to: Optional processor name or ordered names to run afterward.
        handles_failure: Whether failed-command output can be compressed safely.
        wants_exit_code: Whether process accepts the optional exit_code keyword.
        name: Stable identifier used for routing, configuration, and tracking.
    """

    priority: int = 50
    hook_patterns: list[str] = []
    chain_to: str | list[str] | None = None

    #: Whether this processor is safe to run on the output of a *failed*
    #: command (non-zero exit code).
    #:
    #: Most processors summarize the happy path: they recognize a known output
    #: shape and drop what doesn't match.  When a command fails, the
    #: interesting text is usually in an unexpected shape, so summarizing it
    #: risks discarding the very reason the command failed.  The engine
    #: therefore routes failed commands to GenericProcessor — which truncates
    #: with an explicit marker rather than dropping lines silently — unless the
    #: processor opts in here.
    #:
    #: Only set this to True if reporting failures is what the processor is
    #: *for* (test runners, compilers, linters).  ``TestFailureHandling`` in
    #: tests/test_precision.py enforces the claim: every processor with
    #: ``handles_failure = True`` must keep the error lines of a failing run.
    handles_failure: bool = False

    def redacted_secrets(self, command: str, output: str) -> bool:
        """True if ``process(command, output)`` will redact secrets from output.

        The engine's compression-ratio gate exists to protect against a
        processor that made output *worse*: if the result isn't smaller by
        ``min_compression_ratio``, the engine discards it and falls back to
        returning the original, unmodified text.  That's the right call for
        an ordinary processor — but if the processor's job on this call was
        redacting secrets (``API_KEY=***``), "discard the result and fall
        back to the original" means printing the secret in the clear, which
        is worse than not compressing at all.  A processor that returns True
        here for this ``(command, output)`` pair is exempt from that
        fallback for this call: its result is always returned as-is.

        Default False (the common case: nothing to redact).  Override for
        commands/inputs where secrets are actually present — a processor
        that only *sometimes* redacts (e.g. one that handles many file
        types and redacts only a few of them) should check here, not opt in
        for every call.

        Args:
            command: Shell command identifying the input format.
            output: Captured output that may contain sensitive values.

        Returns:
            False by default. Overrides return True when raw fallback could
            disclose values that processing would redact.
        """
        del command, output  # The default processor does not redact any input.
        return False

    #: Whether ``process()`` accepts an ``exit_code`` keyword argument.
    #:
    #: Most processors decide success/failure purely from the shape of the
    #: output text (a recognizable "error"/"FAILED"/traceback marker), which
    #: is enough — the text usually says what happened.  A processor should
    #: only opt in here when the *absence* of a recognizable failure marker
    #: is itself ambiguous (e.g. a build tool that reports failure with a
    #: bare "FAIL" your regex doesn't yet know, or silently via exit status
    #: alone), so it needs the real exit status as a tie-breaker to avoid
    #: summarizing a failed run as a success.  The engine only passes
    #: ``exit_code`` to processors that set this flag; everyone else keeps
    #: the simpler two-argument signature.
    wants_exit_code: bool = False

    def diagnostics(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> diagnostics.Snapshot | None:
        """Optionally describe complete diagnostics for repeated-run comparison.

        This extension does not change ``process()`` or require existing user
        processors to implement it. Callers must sanitize output before parsing.

        Args:
            command: Original command label identifying one supported run.
            output: Captured output after secret redaction.
            exit_code: Command status, or None when unavailable.

        Returns:
            A complete snapshot, or None when comparison is unsupported or
            uncertain. The default declines every input.
        """
        del command, output, exit_code
        return None

    @abc.abstractmethod
    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command belongs to this processor's supported family.
        """

    @abc.abstractmethod
    def process(self, command: str, output: str) -> str:
        """Process and compress the output. Return compressed version.

        Processors that set ``wants_exit_code = True`` may instead declare
        ``def process(self, command: str, output: str, *, exit_code: int |
        None = None) -> str`` — the engine detects the flag and calls
        accordingly.

        Args:
            command: Original shell command used to select output handling.
            output: Captured output before this transformation.

        Returns:
            Compressed text, or the input when no safe reduction is available.
        """

    def clean(self, text: str) -> str:
        """Return text unchanged; subclasses may override light cleanup.

        Args:
            text: Output requiring only low-risk terminal-noise cleanup.

        Returns:
            The input text; overrides may remove formatting noise.
        """
        return text

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the processor name for tracking."""
