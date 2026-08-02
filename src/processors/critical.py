"""The one definition of "a line that must never be silently dropped".

Individual processors each grew their own ``_ERROR_RE`` (a dozen of them, all
slightly different — some miss ``panic``, some miss ``FATAL``, some include
``warning`` and some don't).  That is fine as a *routing* heuristic inside a
processor, but it makes "token-saver never loses critical information" a
per-file convention rather than a property of the system.

This module holds the shared, deliberately broad definition used for the
*safety net*: the generic processor's truncation keeps these lines, and
``tests/test_precision.py`` asserts every processor preserves them.  Being
broad is the right bias here — a false positive costs a few retained lines, a
false negative costs the user the reason their command failed.
"""

from __future__ import annotations

import re

#: Lines matching this are preserved through truncation and asserted on in
#: tests.  Keep it anchored on whole words so ``errorless`` or ``Panicking``
#: don't match by accident, but keep the vocabulary wide.
CRITICAL_RE = re.compile(
    r"\b("
    r"error|errors|failed|failure|failures|fatal|panic|panicked|"
    r"exception|traceback|assert|assertion|denied|refused|timeout|timed"
    r")\b"
    # Common prefixed forms that don't tokenize as words above.
    r"|^\s*(E|FAIL|ERR)\b"
    r"|\b(E[A-Z]{3,}|SIG[A-Z]{3,})\b"  # errno / signal names: ENOENT, SIGKILL
    r"|\[(ERROR|FATAL|CRITICAL)\]"
    r"|\b\w+Error\b"  # ValueError, MigrationError, …
    r"|\b\w+Exception\b",
    re.IGNORECASE,
)


def critical_lines(text: str) -> list[str]:
    """Return the stripped, non-empty lines of ``text`` that look critical."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and CRITICAL_RE.search(ln)]


def missing_critical(original: str, compressed: str) -> list[str]:
    """Return critical lines present in ``original`` but absent from ``compressed``.

    Substring containment (not equality) is deliberate: processors legitimately
    re-indent, prefix, or merge lines, and that should not count as a loss.
    """
    if not original:
        return []
    haystack = compressed
    return [line for line in critical_lines(original) if line not in haystack]
