"""Entry points must survive a non-UTF-8 console.

``print()`` encodes with whatever ``sys.stdout`` was built with.  On Windows
that is the console codepage, and the first Windows CI run died twice on it:
``stats.py`` could not print its ``═`` rule, and ``wrap.py`` could not print
compressed output containing ``\\ufffd``.

Setting ``PYTHONIOENCODING=cp1252`` reproduces that exactly on any OS, which is
what makes these tests worth having on Linux and macOS too — the bug they guard
is invisible there otherwise.  See :mod:`src.console`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent

#: A byte that is valid UTF-8 but has no cp1252 representation, so encoding it
#: raises unless the entry point has forced UTF-8 on its streams.
NON_CP1252 = "═"


def _cp1252_env(**extra: str) -> dict[str, str]:
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", **extra}
    env.pop("PYTHONWARNDEFAULTENCODING", None)
    return env


def _run(args: list[str], env: dict[str, str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


def test_stats_prints_box_drawing_on_a_cp1252_console(tmp_path):
    """stats.py draws a ``═`` rule; cp1252 has no such character."""
    result = _run(
        ["src/stats.py"],
        _cp1252_env(TOKEN_SAVER_DB_DIR=str(tmp_path)),
    )
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_wrap_prints_undecodable_command_output_on_a_cp1252_console():
    """The end-to-end worst case: undecodable *in*, un-encodable *out*.

    ``_run_command`` decodes the command's bytes with ``errors="replace"``,
    which substitutes ``\\ufffd`` — a character cp1252 cannot encode.  So the
    decode-side fix creates the encode-side crash unless both are handled.
    """
    emit = f"{sys.executable} -c \"import sys; sys.stdout.buffer.write(b'ok-\\x80-end')\""
    result = _run(["scripts/wrap.py", emit], _cp1252_env())
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "ok-" in result.stdout
    assert "-end" in result.stdout


#: "café" is a bad probe: its UTF-8 bytes (C3 A9) all *have* cp1252 meanings, so
#: a mis-decode yields mojibake rather than a crash and the test would pass with
#: the bug present.  "❌" encodes to E2 9D 8C, and 0x9D is undefined in cp1252 —
#: the very byte the first Windows CI run named.
UNDECODABLE_IN_CP1252 = "❌"


def test_pretool_hook_still_compresses_a_non_ascii_command_on_a_cp1252_stdin(tmp_path):
    """The hook reads the command as JSON on stdin, and commands contain emoji.

    Asserting "it did not crash" is not enough here, and that is the whole
    lesson of this test: ``UnicodeDecodeError`` subclasses ``ValueError``, which
    ``hook_pretool.main`` already catches to stay fail-open.  So a cp1252 stdin
    does not produce a traceback — it silently produces *no compression at all*,
    for every command containing a non-cp1252 byte.  Only asserting on the
    rewrite catches that.
    """
    command = "git log --grep=❌"
    # ensure_ascii=False matters: the default escapes the emoji to a "❌"
    # sequence, which is pure ASCII and decodes fine under cp1252 — the test
    # would then pass with the bug present.  Claude Code sends the raw bytes.
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}, ensure_ascii=False
    )
    assert UNDECODABLE_IN_CP1252 in payload
    assert b"\x9d" in payload.encode("utf-8")

    result = _run(
        ["scripts/hook_pretool.py"],
        _cp1252_env(TOKEN_SAVER_DB_DIR=str(tmp_path)),
        stdin=payload,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "hook emitted no decision — it silently declined to compress"
    decision = json.loads(result.stdout)
    rewritten = decision["hookSpecificOutput"]["updatedInput"]["command"]
    assert "wrap.py" in rewritten
    assert command in rewritten, f"the emoji did not survive the round trip: {rewritten!r}"
