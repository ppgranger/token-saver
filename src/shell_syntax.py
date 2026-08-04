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


def has_output_redirection(command: str) -> bool:
    """Return True if an unquoted output redirection (``>``, ``>>``, ``2>``) is present.

    A ``>`` inside quotes (``git commit -m "fixes >50%"``) is ignored, and the
    arrow/comparison operators ``->`` and ``=>`` are not redirections.
    """
    for i, ch in iter_unquoted(command):
        if ch == ">":
            prev = command[i - 1] if i > 0 else ""
            if prev not in ("-", "="):
                return True
    return False
