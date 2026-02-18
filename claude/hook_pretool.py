#!/usr/bin/env python3
"""PreToolUse hook for Claude Code.

Reads JSON from stdin, rewrites compressible commands to go through wrap.py.
Uses shlex.quote() to prevent shell injection when rewriting.
"""

import json
import logging
import os
import re
import shlex
import sys

# --- Debug logging (writes to ~/.token-saver/hook.log when TOKEN_SAVER_DEBUG=true) ---
_log = logging.getLogger("token-saver.hook_pretool")
_log.setLevel(logging.DEBUG)
_debug = os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes")
if _debug:
    _log_dir = os.path.join(os.path.expanduser("~"), ".token-saver")
    os.makedirs(_log_dir, exist_ok=True)
    _handler = logging.FileHandler(os.path.join(_log_dir, "hook.log"))
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
else:
    _log.addHandler(logging.NullHandler())


# Build patterns from processor registry (auto-discovered)
def _load_compressible_patterns() -> list[str]:
    """Import hook_patterns from the processor registry."""
    # Add extension root to path so we can import the src package
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _extension_root = os.path.dirname(_this_dir)
    _log.debug("this_dir=%s, extension_root=%s", _this_dir, _extension_root)
    if _extension_root not in sys.path:
        sys.path.insert(0, _extension_root)
    from src.processors import collect_hook_patterns  # noqa: PLC0415

    patterns = collect_hook_patterns()
    _log.debug("Loaded %d compressible patterns", len(patterns))
    return patterns


try:
    COMPRESSIBLE_PATTERNS = _load_compressible_patterns()
except Exception:
    _log.exception("Failed to load compressible patterns")
    raise
COMPILED_PATTERNS = [re.compile(p) for p in COMPRESSIBLE_PATTERNS]

# Commands that should NEVER be wrapped
# We check these on the raw command string (before splitting)
EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # unquoted pipe
    r"(?<!['\"])&&(?!['\"])",  # unquoted &&
    r"(?<!['\"])\|\|(?!['\"])",  # unquoted ||
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*(ssh|scp|rsync)\b",
    r"token.saver",  # avoid wrapping ourselves
    r"wrap\.py",
    r">\s",  # redirections
    r"<\(",  # process substitution
    r"^\s*sudo\b",  # never wrap sudo
    r"^\s*env\s+\S+=",  # env VAR=val prefix — too complex to wrap
]

COMPILED_EXCLUDED = [re.compile(p) for p in EXCLUDED_PATTERNS]


def is_compressible(command: str) -> bool:
    """Check if a command should be compressed."""
    cmd = command.strip()
    if not cmd:
        return False
    for pattern in COMPILED_EXCLUDED:
        if pattern.search(cmd):
            return False
    return any(pattern.search(cmd) for pattern in COMPILED_PATTERNS)


def main():
    try:
        raw_input = sys.stdin.read()
        _log.debug("stdin: %s", raw_input[:500])
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError) as exc:
        _log.debug("Invalid JSON input: %s", exc)
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        _log.debug("Skipping non-Bash tool: %s", tool_name)
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command or not is_compressible(command):
        _log.debug("Not compressible: %r", command[:200])
        sys.exit(0)

    # Build path to wrap.py (same directory)
    wrap_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrap.py")
    if not os.path.isfile(wrap_py):
        _log.warning("wrap.py not found at %s", wrap_py)
        sys.exit(0)  # Fail open — don't break the command

    # Rewrite: pass the original command as a single quoted argument to avoid injection
    new_command = f"python3 {shlex.quote(wrap_py)} {shlex.quote(command)}"
    _log.debug("Rewriting: %r -> %r", command, new_command)

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {"command": new_command},
        },
    }

    json.dump(result, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
