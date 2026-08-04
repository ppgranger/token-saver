"""Make stdout/stderr UTF-8 regardless of the console's codepage.

The decoding side of this problem is handled at each call site (``encoding=``
on every ``open``/``subprocess``).  This module is the *encoding* side, and it
has to live at the entry points instead: ``print()`` encodes with whatever
``sys.stdout`` was built with, which on Windows is the console codepage —
cp1252 on the GitHub runner.

That is not hypothetical.  Both of these crashed on the first Windows CI run:

* ``src/stats.py`` prints a ``═`` rule, and cp1252 has no such character;
* ``scripts/wrap.py`` prints the compressed command output, which contains
  whatever the wrapped command emitted — including the ``\\ufffd`` that our own
  ``errors="replace"`` decoding introduces for undecodable bytes.

``errors="replace"`` mirrors the decode side for the same reason: a mangled
character is a bad outcome, losing the user's command is a worse one.
"""

from __future__ import annotations

import contextlib
import sys


def use_utf8_io() -> None:
    """Reconfigure stdin/stdout/stderr to UTF-8.  Safe to call more than once.

    ``stdin`` is included because the hooks receive the command as a JSON
    payload on it: Claude Code sends UTF-8, cp1252 cannot decode much of it,
    and ``git commit -m "café"`` would take the hook down before it ever
    reached a processor.

    Silently does nothing when the streams cannot be reconfigured — under
    pytest's ``capsys`` they are substituted with objects that have no
    ``reconfigure``, and a crash there would be a worse bug than the one this
    prevents.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        # Detached or already-closed stream; nothing useful to do about it.
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")
