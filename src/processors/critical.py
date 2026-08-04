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

#: Lines matching either pattern are preserved through truncation and
#: asserted on in tests.  Split in two so the freewheeling, human-vocabulary
#: half (``_CRITICAL_CI``) doesn't drag the terse, symbol-shaped half
#: (``_CRITICAL_CS``) into case-insensitivity with it.
#:
#: A single ``re.IGNORECASE`` pattern covering both used to mean
#: ``E[A-Z]{3,}`` — meant for errno/signal names like ``ENOENT`` — also
#: matched ordinary words such as ``Extracting``, ``Emitted`` or ``Entry``
#: the moment they appeared in fixed-width or capitalized output. Since
#: both consumers of this module cap how many "critical" lines they keep
#: (``generic_keep_critical`` / ``recover_critical_lines``, default 20),
#: that noise could fill the cap and push the real error out — the exact
#: failure this module exists to prevent.
#:
#: Keep it anchored on whole words so ``errorless`` or ``Panicking`` don't
#: match by accident, but keep the vocabulary wide.
_CRITICAL_CI = re.compile(
    r"\b("
    r"error|errors|failed|failure|failures|fatal|panic|panicked|"
    r"exception|traceback|assert|assertion|denied|refused|timeout|timed"
    r")\b"
    r"|^\s*(FAIL|ERR)\b"  # prefixed forms that don't tokenize as words above
    r"|\[(ERROR|FATAL|CRITICAL)\]"
    r"|\b\w+Error\b"  # ValueError, MigrationError, …
    r"|\b\w+Exception\b",
    re.IGNORECASE,
)

#: Case-sensitive: these are shouty by convention (errno/signal names,
#: compiler-style bare ``E`` prefixes), and folding case turns them into
#: false-positive magnets on any line that happens to contain a capital
#: letter run.  ``FAIL``/``ERR`` deliberately stay in the case-insensitive
#: half above — real-world tools print ``fail:``/``err:`` in lowercase too,
#: and neither is a two-character alternation vulnerable to noise.
_CRITICAL_CS = re.compile(
    r"^\s*E\b"  # compiler/traceback bare E prefix: "E   AssertionError: ..."
    r"|\b(E[A-Z]{3,}|SIG[A-Z]{3,})\b"  # errno / signal names: ENOENT, SIGKILL
)


def is_critical(line: str) -> bool:
    """True if ``line`` looks like it reports a failure worth preserving."""
    return bool(_CRITICAL_CI.search(line) or _CRITICAL_CS.search(line))


def critical_lines(text: str) -> list[str]:
    """Return the stripped, non-empty lines of ``text`` that look critical."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and is_critical(ln)]


def missing_critical(original: str, compressed: str) -> list[str]:
    """Return critical lines present in ``original`` but absent from ``compressed``.

    Substring containment (not equality) is deliberate: processors legitimately
    re-indent, prefix, or merge lines, and that should not count as a loss.
    """
    if not original:
        return []
    haystack = compressed
    return [line for line in critical_lines(original) if line not in haystack]
