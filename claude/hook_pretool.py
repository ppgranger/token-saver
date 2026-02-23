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

# Ensure the extension root is importable (claude/ -> extension/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chain_utils import CHAIN_SPLIT_RE, SILENT_CMDS_RE, split_chain

# --- Debug logging (writes to data_dir/hook.log when TOKEN_SAVER_DEBUG=true) ---
_log = logging.getLogger("token-saver.hook_pretool")
_log.setLevel(logging.DEBUG)
_debug = os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes")
if _debug:
    from src import data_dir as _data_dir

    _log_dir = _data_dir()
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

# Trailing pipe suffixes that are safe to wrap.
# These are stripped before checking exclusions so commands like
# `git log | head -30` or `pip list | grep torch` are still compressed.
# The full original command (with pipe) is passed to wrap.py unchanged.
#
# Allowed trailing pipes (single stage only):
#   | head [-N]              — truncate output
#   | tail [-N] [+N]         — truncate output
#   | wc [-l] [-w] [-c]      — count lines/words/chars
#   | grep [-viEc] "pattern" — filter lines (single grep, no chaining)
#   | sort [-rnk] [N]        — reorder lines
#   | uniq [-c]              — deduplicate lines
#   | cut -fN [-dX]          — extract columns
_SAFE_TRAILING_PIPE_RE = re.compile(
    r"\s*\|\s*("
    r"head(\s+-[n]?\s*\d+|\s+-\d+)*"  # | head -30, | head -n 50
    r"|tail(\s+[-+]?\d+|\s+-[nf]\s*\d+)*"  # | tail -20, | tail -n 50, | tail +5
    r"|wc(\s+-[lwc])*"  # | wc -l, | wc -w
    r"|grep(\s+-[viEcwnHr])*\s+\S+"  # | grep -i pattern, | grep -v noise
    r"|sort(\s+-[rnktu](\s+\d+)?)*"  # | sort -r, | sort -k 2
    r"|uniq(\s+-[cd])*"  # | uniq -c
    r"|cut(\s+-[fd]\s*\S+)+"  # | cut -f1 -d,
    r")\s*$"
)

# Commands that should NEVER be wrapped (checked on whole command for
# single-command inputs, or delegated to per-segment checks for chains).
EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # unquoted pipe (complex pipelines)
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*(ssh|scp|rsync)\b",
    r"(?:^|\s)token[-_]saver\s",  # avoid wrapping token-saver CLI itself
    r"wrap\.py",
    r">\s",  # redirections
    r"<\(",  # process substitution
    r"^\s*sudo\b",  # never wrap sudo
    r"^\s*env\s+\S+=",  # env VAR=val prefix — too complex to wrap
]

COMPILED_EXCLUDED = [re.compile(p) for p in EXCLUDED_PATTERNS]

# Per-segment safety checks applied inside _is_chain_compressible().
# These catch dangerous constructs within individual chain segments.
_SEGMENT_EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # pipes inside a segment
    r">\s",  # redirections
    r"<\(",  # process substitution
    r"^\s*sudo\b",
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*(ssh|scp|rsync)\b",
    r"^\s*env\s+\S+=",
    r"(?:^|\s)token[-_]saver\s",
    r"wrap\.py",
]

_COMPILED_SEGMENT_EXCLUDED = [re.compile(p) for p in _SEGMENT_EXCLUDED_PATTERNS]


def _is_segment_safe(segment: str) -> bool:
    """Return True if a single chain segment has no dangerous constructs."""
    return all(not pattern.search(segment) for pattern in _COMPILED_SEGMENT_EXCLUDED)


def _is_chain_compressible(command: str) -> bool:
    """Check whether a chained command (&&/;) is compressible.

    Every segment must be safe AND either compressible or silent.
    At least one segment must be compressible (all-silent chains are rejected).
    Safe trailing pipes are only stripped from the *last* segment.
    """
    segments = split_chain(command)
    if not segments:
        return False

    has_compressible = False
    for i, seg in enumerate(segments):
        # Only strip safe trailing pipe from the last segment
        check_seg = _SAFE_TRAILING_PIPE_RE.sub("", seg) if i == len(segments) - 1 else seg
        if not _is_segment_safe(check_seg):
            return False
        is_silent = bool(SILENT_CMDS_RE.match(check_seg))
        is_comp = any(p.search(check_seg) for p in COMPILED_PATTERNS)
        if not is_silent and not is_comp:
            return False  # unknown command in chain -> reject
        if is_comp:
            has_compressible = True

    return has_compressible


def is_compressible(command: str) -> bool:
    """Check if a command should be compressed.

    Safe trailing pipes (| head, | tail, | wc) are stripped before checking
    exclusions, so that e.g. ``git log | head -30`` is still compressible.
    The full original command (with the pipe) is passed to wrap.py.

    Chained commands (&&, ;) are split and each segment is validated
    individually.  ``||`` chains are always rejected.
    """
    cmd = command.strip()
    if not cmd:
        return False

    # || is always rejected (error-recovery chains are too complex)
    if re.search(r"(?<!['\"])\|\|(?!['\"])", cmd):
        return False

    # Detect chains (&&, ;) BEFORE stripping safe trailing pipes,
    # so that mid-chain pipes are not accidentally stripped.
    if CHAIN_SPLIT_RE.search(cmd):
        return _is_chain_compressible(cmd)

    # Single command — strip safe trailing pipes for exclusion check only
    check_cmd = _SAFE_TRAILING_PIPE_RE.sub("", cmd)
    for pattern in COMPILED_EXCLUDED:
        if pattern.search(check_cmd):
            return False
    return any(pattern.search(check_cmd) for pattern in COMPILED_PATTERNS)


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

    # Pass Claude Code's session_id so all compressions in the same Claude
    # session share one tracker session.  We embed it as an env var prefix in
    # the rewritten command so it propagates to the wrap.py subprocess.
    cc_session = input_data.get("session_id", "")

    # Rewrite: pass the original command as a single quoted argument to avoid injection
    python = "python" if os.name == "nt" else "python3"
    session_prefix = f"TOKEN_SAVER_SESSION={shlex.quote(cc_session)} " if cc_session else ""
    new_command = f"{session_prefix}{python} {shlex.quote(wrap_py)} {shlex.quote(command)}"
    _log.debug("Rewriting: %r -> %r (session=%s)", command, new_command, cc_session)

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
