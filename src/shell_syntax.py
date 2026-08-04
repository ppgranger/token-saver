"""Quote-aware scanning of shell command strings.

Four separate functions used to re-implement the same "walk the string,
skipping single- and double-quoted regions" loop: both chain splitters here in
``chain_utils``, plus the dangerous-construct and output-redirection checks in
``scripts/hook_pretool.py``.  They agreed by luck, and a fix to one never
reached the others.

Everything that needs to reason about unquoted shell syntax now goes through
:func:`iter_unquoted`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_QUOTES = ("'", '"')


def iter_unquoted(command: str) -> Iterator[tuple[int, str]]:
    """Yield ``(index, char)`` for every character outside a quoted region.

    Quoted regions are skipped wholesale, including their delimiters.
    Backslash escapes are honoured inside double quotes but not single quotes,
    matching POSIX: ``"a\\"b"`` is one region, while ``'a\\'`` ends at its
    second quote.  The two previous implementations each got exactly one of
    those cases right — the chain splitters ignored escapes entirely (wrong
    for double quotes), the hook checks applied them to both (wrong for
    single).

    An unterminated quote swallows the rest of the string: the safe direction,
    since we then find no operators and decline to wrap the command.
    """
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch in _QUOTES:
            quote = ch
            escapes = quote == '"'
            i += 1
            while i < n and command[i] != quote:
                if escapes and command[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            i += 1  # past the closing quote (or past the end)
            continue
        yield i, ch
        i += 1


def has_unquoted(command: str, constructs: tuple[str, ...]) -> bool:
    """Return True if any of ``constructs`` starts outside a quoted region.

    Occurrences nested inside quotes (e.g. inside ``git commit -m "..."``) are
    tolerated: they don't affect chain splitting or per-segment execution.
    """
    return any(command.startswith(c, i) for i, _ in iter_unquoted(command) for c in constructs)


#: ``2>&1``, ``>&2``, ``>&-`` duplicate a file descriptor onto another —
#: no file is written, so they are not an output redirection.  Anchored at
#: the ``>`` and requiring the tail to be exactly digits-or-dash followed by
#: a non-identifier boundary, so ``>&2foo`` (which bash does NOT treat as a
#: dup — see below) still counts as a real redirection instead of being
#: waved through.
_FD_DUP_TAIL_RE = re.compile(r">&(\d+|-)(?![\w./-])")


def has_output_redirection(command: str) -> bool:
    """Return True if an unquoted output redirection (``>``, ``>>``, ``2>``) is present.

    A ``>`` inside quotes (``git commit -m "fixes >50%"``) is ignored, the
    arrow/comparison operators ``->`` and ``=>`` are not redirections, and
    neither is a file-descriptor duplication (``2>&1``, ``>&2``, ``>&-``) —
    those redirect one stream onto another already-open one; they don't open
    or write a new file, so a command using only them is still safe to wrap.
    """
    for i, ch in iter_unquoted(command):
        if ch == ">":
            prev = command[i - 1] if i > 0 else ""
            if prev in ("-", "="):
                continue
            if _FD_DUP_TAIL_RE.match(command, i):
                continue
            return True
    return False


def has_unquoted_background_operator(command: str) -> bool:
    """Return True if command contains a standalone unquoted ``&`` (job
    control's "run in background" operator), as opposed to ``&&`` (logical
    AND), ``>&``/``N>&M`` (fd duplication), or ``&>`` (combined redirect).

    A backgrounded command detaches from ``wrap.py``'s subprocess: the
    ``Popen`` call returns as soon as the shell forks it, so there is nothing
    to compress, and the detached process keeps running with no supervisor —
    invisible to the timeout that would otherwise reclaim it.
    """
    n = len(command)
    for i, ch in iter_unquoted(command):
        if ch != "&":
            continue
        prev = command[i - 1] if i > 0 else ""
        nxt = command[i + 1] if i + 1 < n else ""
        if prev == "&" or nxt == "&":
            continue  # part of &&
        if prev == ">" or nxt == ">":
            continue  # part of N>&M (dup) or &>file (combined redirect)
        return True
    return False


#: A segment that *opens* a compound statement (``for x in ...``, ``if ...``,
#: ``while ...``) is not a complete, independent command — it is the first
#: fragment of one.  These are POSIX reserved words; no real command is
#: literally named ``for``/``while``/``until``/``if``/``case``/``select``, so
#: this has no false-positive surface.  Naive chain splitting on unquoted
#: ``&&``/``;`` cannot tell a real chain from a for-loop's internal ``;``
#: separators, so ``for f in a b; do echo $f; done`` gets shattered into
#: multiple "segments"; wrapping each independently in its own brace group is
#: a shell syntax error — the user's command would never run at all, wrapped
#: or not.  Rejecting on the *opening* fragment is enough: it's always the
#: first segment produced by the bad split, so catching it there declines to
#: wrap the whole command before any damage is done.
_SHELL_CONSTRUCT_OPEN_RE = re.compile(r"^\s*(for|while|until|if|case|select)\b")


def has_shell_construct_open(segment: str) -> bool:
    """True if ``segment`` starts with a compound-statement reserved word."""
    return bool(_SHELL_CONSTRUCT_OPEN_RE.match(segment))


def has_unquoted_newline(command: str) -> bool:
    """Return True if command contains an unquoted, non-continuation newline.

    A multi-line ``command`` string is not a single shell statement — it is
    several, and every per-segment safety check in ``hook_pretool.py`` (no
    sudo, no bare REPL, no redirection, …) only ever inspects the segments
    produced by splitting on ``&&``/``;``.  A newline is a statement
    separator too, so a line hidden after one bypasses every one of those
    checks, and — independently — the compressed output ends up representing
    only the first line, silently discarding the rest.

    A newline directly preceded by an unescaped trailing backslash is a line
    *continuation* (``cmd \\``, newline, ``more args``) — POSIX shells join it
    with the next line before parsing, so it is not a statement boundary and
    is not flagged.  An escaped backslash (``\\\\``, an even run) does not
    continue the line, matching ``_ends_with_line_continuation`` in
    ``hook_pretool.py``.
    """
    for i, ch in iter_unquoted(command):
        if ch != "\n":
            continue
        before = command[:i]
        trailing_backslashes = len(before) - len(before.rstrip("\\"))
        if trailing_backslashes % 2 == 1:
            continue  # escaped: a genuine line continuation
        return True
    return False
