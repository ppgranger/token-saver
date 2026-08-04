"""Abstract base class for output processors."""

from abc import ABC, abstractmethod

# Matches any Python invocation: python, python3, python3.11,
# .venv/bin/python3, /usr/bin/python, etc.
PYTHON_CMD = r"(?:\S+/)?python[23]?(?:\.\d+)?"


class Processor(ABC):
    """Base class for all output processors.

    Subclasses must set ``priority`` and ``hook_patterns`` as class-level
    attributes so the registry can auto-discover, order, and collect patterns.

    Priority conventions:
        10-19  High priority overrides (e.g. PackageListProcessor before build)
        20-29  Core processors (git, test, build, lint)
        30-49  Specialized (network, docker, kubectl, terraform, env, search, system_info)
        50-69  Content-based (file_listing, file_content)
        999    Generic fallback (must always be last)
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
        """
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

    @abstractmethod
    def can_handle(self, command: str) -> bool:
        """Return True if this processor can handle the given command."""

    @abstractmethod
    def process(self, command: str, output: str) -> str:
        """Process and compress the output. Return compressed version.

        Processors that set ``wants_exit_code = True`` may instead declare
        ``def process(self, command: str, output: str, *, exit_code: int |
        None = None) -> str`` — the engine detects the flag and calls
        accordingly.
        """

    def clean(self, text: str) -> str:
        """Light cleanup pass (default: no-op). Overridden by GenericProcessor."""
        return text

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the processor name for tracking."""
