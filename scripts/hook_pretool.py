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

# Ensure the extension root is importable (scripts/ -> plugin root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chain_utils import CHAIN_SPLIT_RE, split_chain
from src.console import use_utf8_io
from src.shell_syntax import (
    has_output_redirection,
    has_shell_construct_open,
    has_unquoted,
    has_unquoted_background_operator,
    has_unquoted_newline,
)

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
    # Fail open, like every other error path in this project.  A broken
    # processor — most likely a user one under ~/.token-saver/processors/ —
    # must not take down *every* Bash command in the session.  With no
    # patterns loaded nothing matches, so commands run unwrapped.
    _log.exception("Failed to load compressible patterns — compression disabled")
    COMPRESSIBLE_PATTERNS = []


def _compile_patterns(patterns: list[str]) -> tuple[list[str], list[re.Pattern]]:
    """Compile patterns one by one, dropping (and logging) any invalid one.

    Returns the sources and the compiled patterns as two parallel lists, so
    ``_matched_compressible`` can still zip them to report *which* source
    regex matched.
    """
    sources: list[str] = []
    compiled: list[re.Pattern] = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error:  # noqa: PERF203 — per-pattern isolation is the point, ~50 items once
            _log.exception("Skipping invalid hook pattern %r", p)
        else:
            sources.append(p)
    return sources, compiled


COMPRESSIBLE_PATTERNS, COMPILED_PATTERNS = _compile_patterns(COMPRESSIBLE_PATTERNS)

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

# Streaming / follow / watch commands that never terminate on their own.
# Wrapping them would buffer forever (the wrap.py subprocess only flushes
# after the child exits), so they must pass through untouched.  Shared by
# both the whole-command and per-segment exclusion lists.
_STREAMING_EXCLUDED_PATTERNS = [
    r"^\s*watch\b",  # `watch` repeats a command forever
    r"\s--follow(=|\s|$)",  # --follow on tail/journalctl/kubectl/docker logs
    r"^\s*tail\b[^|]*\s-[a-zA-Z]*[fF]\b",  # tail -f / tail -F / tail -nf
    r"^\s*journalctl\b[^|]*\s-[a-zA-Z]*f\b",  # journalctl -f
    r"\b(kubectl|oc)\b[^|]*\blogs\b[^|]*\s-[a-zA-Z]*f\b",  # kubectl/oc logs -f
    r"\bdocker\b[^|]*\blogs\b[^|]*\s-[a-zA-Z]*f\b",  # docker logs -f
    r"^\s*docker\s+stats\b(?![^|]*--no-stream)",  # docker stats (live by default)
    r"^\s*docker(\s+compose|-compose)\s+up\b(?![^|]*\s-d\b)",  # compose up (attached)
    r"\s--watch(=|\s|$)",  # generic --watch flag (vitest, jest, tsc, etc.)
    r"\s--watchAll\b",  # jest --watchAll
    r"^\s*(npx\s+)?vitest\b(?![^|]*\brun\b)",  # vitest defaults to watch mode
]

# Commands that should NEVER be wrapped (checked on whole command for
# single-command inputs, or delegated to per-segment checks for chains).
EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # unquoted pipe (complex pipelines)
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*ssh\s+(?:-\S+\s+)*\S+\s*$",  # interactive ssh only (no remote command)
    r"^\s*rsync\b.*\S+:\S+",  # only exclude remote rsync (host:path)
    r"(?:^|\s)token[-_]saver\s",  # avoid wrapping token-saver CLI itself
    # Recursion guard: our rewrite is `python3 <…>wrap.py '<cmd>'`.  Match
    # wrap.py only in script-execution position so `cat wrap.py` stays wrappable.
    r"(?:^|\s)(?:\S*/)?(?:python\d?(?:\.\d+)*|node|ruby|sh|bash|zsh|perl)\s+"
    r"(?:-\S+\s+)*\S*wrap\.py\b",
    r"^\s*\.?\S*/?wrap\.py\b",
    r"<\(",  # process substitution
    r"^\s*sudo\b",  # never wrap sudo
    r"^\s*env\s+\S+=",  # env VAR=val prefix — too complex to wrap
    # Interactive-flag REPLs even with script args (e.g. `python -i script.py`).
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|ruby|perl|ghci|deno|php|lua|R|bash|sh|zsh)"
    r"\s+(?:-\S*i\S*|--interactive)(\s|$)",
    *_STREAMING_EXCLUDED_PATTERNS,
]

COMPILED_EXCLUDED = [re.compile(p) for p in EXCLUDED_PATTERNS]

# Strip leading path prefix so '/usr/bin/git status' → 'git status',
# './node_modules/.bin/jest' → 'jest', '.venv/bin/pip' → 'pip', etc.
# Greedy match: captures everything up to and including the last '/'
# in the first token (before any space).
_PATH_PREFIX_RE = re.compile(r"^(\S*/)(?=\S)")


def _normalize_cmd(cmd: str) -> str:
    """Strip leading path prefix for pattern matching."""
    return _PATH_PREFIX_RE.sub("", cmd)


# Constructs that break naive chain splitting / per-segment execution.
_DANGEROUS_CONSTRUCTS = ("$(", "`", "<<")

# Both checks now share the single quote-aware scanner in src.shell_syntax,
# alongside the chain splitters.  Re-exported under the historical names so
# the rest of this module (and its tests) read unchanged.
_has_unquoted_construct = has_unquoted
_has_output_redirection = has_output_redirection


# Per-segment safety checks applied inside _is_chain_compressible().
# These catch dangerous constructs within individual chain segments.
_SEGMENT_EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # pipes inside a segment
    r"<\(",  # process substitution
    r"^\s*sudo\b",
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*ssh\s+(?:-\S+\s+)*\S+\s*$",  # interactive ssh only
    r"^\s*rsync\b.*\S+:\S+",  # only exclude remote rsync (host:path)
    r"^\s*env\s+\S+=",
    r"(?:^|\s)token[-_]saver\s",
    r"(?:^|\s)(?:\S*/)?(?:python\d?(?:\.\d+)*|node|ruby|sh|bash|zsh|perl)\s+"
    r"(?:-\S+\s+)*\S*wrap\.py\b",
    r"^\s*\.?\S*/?wrap\.py\b",
    # Bare interactive REPL launchers: would hang waiting for stdin.
    # Only matches when there are no arguments (REPL mode).
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|bash|sh|zsh|ruby|irb|pry|gdb|lldb"
    r"|mongo|mongosh|redis-cli|psql|mysql|sqlite3|php|perl|lua|R)\s*$",
    # Interactive-flag REPLs: -i drops into REPL even with other args.
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|ruby|perl|ghci|deno|php|lua|R|bash|sh|zsh)"
    r"\s+(?:-\S*i\S*|--interactive)(\s|$)",
    *_STREAMING_EXCLUDED_PATTERNS,
]

_COMPILED_SEGMENT_EXCLUDED = [re.compile(p) for p in _SEGMENT_EXCLUDED_PATTERNS]


def _ends_with_line_continuation(segment: str) -> bool:
    """Return True if the segment ends with an unescaped backslash.

    ``wrap.py`` closes each chain segment's brace group with a newline; a
    trailing backslash would splice that newline away and swallow the closing
    brace.  An even-length run of backslashes is an escaped backslash, not a
    continuation.
    """
    stripped = segment.rstrip()
    trailing = len(stripped) - len(stripped.rstrip("\\"))
    return trailing % 2 == 1


def _is_comment_only(segment: str) -> bool:
    """Return True if the segment is nothing but a shell comment.

    Such a segment would produce an empty brace group (``{ # foo\\n}``), which
    is a syntax error.  Today it also silently comments out the rest of the
    rewritten line, so the command never runs — either way, don't wrap it.
    """
    return segment.lstrip().startswith("#")


def _is_segment_safe(segment: str) -> bool:
    """Return True if a single chain segment has no dangerous constructs.

    Checks both the raw segment and its path-stripped form, so commands like
    ``/usr/bin/vim``, ``./python``, or ``.venv/bin/sudo`` are still caught.
    """
    if _has_output_redirection(segment):
        return False
    # A backgrounded segment (`npm run dev &`) detaches from wrap.py's
    # subprocess entirely — nothing to compress, and the timeout can never
    # reclaim a process it no longer has a handle on.
    if has_unquoted_background_operator(segment):
        return False
    # An opening fragment of a for/while/if/case/... compound statement is
    # not a real, independent segment: the chain splitter only saw one of
    # its internal `;`s.  Wrapping it in its own brace group is a shell
    # syntax error, so the whole command — every segment, not just this
    # one — must be declined.  See has_shell_construct_open's docstring.
    if has_shell_construct_open(segment):
        return False
    # Both break wrap.py's brace-group rewrite — see the helpers above.
    if _ends_with_line_continuation(segment) or _is_comment_only(segment):
        return False
    norm = _normalize_cmd(segment)
    for pattern in _COMPILED_SEGMENT_EXCLUDED:
        if pattern.search(segment) or pattern.search(norm):
            return False
    return True


def _is_chain_compressible(command: str) -> bool:
    """Check whether a chained command (&&/;) is compressible.

    Every segment must pass the segment safety check (no sudo, redirects,
    bare REPLs, etc.).  At least one segment must be compressible; the
    others may be silent or unknown (their output passes through unchanged
    in wrap.py's per-segment compression).  Safe trailing pipes are only
    stripped from the *last* segment.
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
        norm_seg = _normalize_cmd(check_seg)
        is_comp = any(p.search(check_seg) for p in COMPILED_PATTERNS) or any(
            p.search(norm_seg) for p in COMPILED_PATTERNS
        )
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

    # A newline is a statement separator the chain splitter never sees (it
    # only splits on && / ;), so a hidden second line bypasses every
    # per-segment safety check below AND has its output silently discarded
    # by wrap.py, which only ever compresses the first line as "the" command.
    if has_unquoted_newline(cmd):
        return False

    # Reject commands with unquoted $(), backticks, or heredocs — these break
    # naive chain splitting and per-segment execution.  Quoted occurrences
    # (e.g. inside `git commit -m "$(...)"`) are tolerated.
    if _has_unquoted_construct(cmd, _DANGEROUS_CONSTRUCTS):
        return False

    # Detect chains (&&, ;) BEFORE stripping safe trailing pipes,
    # so that mid-chain pipes are not accidentally stripped.
    if CHAIN_SPLIT_RE.search(cmd):
        return _is_chain_compressible(cmd)

    # Output redirections (quote-aware) are never wrapped.
    if _has_output_redirection(cmd):
        return False

    # A backgrounded command (`npm run dev &`) detaches immediately; there is
    # no output to compress and no way for wrap.py's timeout to reclaim it.
    if has_unquoted_background_operator(cmd):
        return False

    # Single command — strip safe trailing pipes for exclusion check only
    check_cmd = _SAFE_TRAILING_PIPE_RE.sub("", cmd)
    # Check exclusions against both raw and path-stripped forms, so
    # path-prefixed launchers (/usr/bin/vim, ./python) are still caught.
    norm_cmd = _normalize_cmd(check_cmd)
    for pattern in COMPILED_EXCLUDED:
        if pattern.search(check_cmd) or pattern.search(norm_cmd):
            return False
    return any(pattern.search(check_cmd) for pattern in COMPILED_PATTERNS) or any(
        pattern.search(norm_cmd) for pattern in COMPILED_PATTERNS
    )


def _matched_exclusion(check_cmd: str, norm_cmd: str) -> str | None:
    """Return the source regex of the first exclusion that matches, if any."""
    for src, pattern in zip(EXCLUDED_PATTERNS, COMPILED_EXCLUDED, strict=False):
        if pattern.search(check_cmd) or pattern.search(norm_cmd):
            return src
    return None


def _matched_compressible(check_cmd: str, norm_cmd: str) -> list[str]:
    """Return source regexes of all compressible patterns that match."""
    matched = []
    for src, pattern in zip(COMPRESSIBLE_PATTERNS, COMPILED_PATTERNS, strict=False):
        if pattern.search(check_cmd) or pattern.search(norm_cmd):
            matched.append(src)
    return matched


def explain_decision(command: str) -> dict:
    """Explain whether ``command`` would be wrapped, and why.

    Mirrors ``is_compressible`` step-for-step but returns a structured record
    instead of a bool, so ``token-saver explain`` can show the routing/exclusion
    decision. Keys: command, compressible, reason, excluded_by,
    matched_patterns, is_chain.
    """
    result = {
        "command": command,
        "compressible": False,
        "reason": "",
        "excluded_by": None,
        "matched_patterns": [],
        "is_chain": False,
    }
    cmd = command.strip()
    if not cmd:
        result["reason"] = "empty command"
        return result

    if re.search(r"(?<!['\"])\|\|(?!['\"])", cmd):
        result["reason"] = "contains '||' (error-recovery chains are not wrapped)"
        result["excluded_by"] = r"||"
        return result

    if has_unquoted_newline(cmd):
        result["reason"] = "contains an unquoted newline (multiple statements)"
        result["excluded_by"] = "unquoted newline"
        return result

    if _has_unquoted_construct(cmd, _DANGEROUS_CONSTRUCTS):
        result["reason"] = "contains unquoted $(), backtick, or heredoc"
        result["excluded_by"] = "dangerous shell construct"
        return result

    if CHAIN_SPLIT_RE.search(cmd):
        result["is_chain"] = True
        compressible = _is_chain_compressible(cmd)
        result["compressible"] = compressible
        seen: list[str] = []
        for seg in split_chain(cmd):
            check_seg = _SAFE_TRAILING_PIPE_RE.sub("", seg)
            norm_seg = _normalize_cmd(check_seg)
            for p in _matched_compressible(check_seg, norm_seg):
                if p not in seen:
                    seen.append(p)
        result["matched_patterns"] = seen
        result["reason"] = (
            "chain with at least one compressible, all-safe segment"
            if compressible
            else "chain has an unsafe segment or no compressible segment"
        )
        return result

    if _has_output_redirection(cmd):
        result["reason"] = "contains output redirection (>, >>, 2>, &>)"
        result["excluded_by"] = "output redirection"
        return result

    if has_unquoted_background_operator(cmd):
        result["reason"] = "contains an unquoted '&' (backgrounded command)"
        result["excluded_by"] = "background operator"
        return result

    check_cmd = _SAFE_TRAILING_PIPE_RE.sub("", cmd)
    norm_cmd = _normalize_cmd(check_cmd)
    excl = _matched_exclusion(check_cmd, norm_cmd)
    if excl is not None:
        result["reason"] = "matched an exclusion pattern"
        result["excluded_by"] = excl
        return result

    matched = _matched_compressible(check_cmd, norm_cmd)
    result["matched_patterns"] = matched
    result["compressible"] = bool(matched)
    result["reason"] = (
        "matched a compressible processor pattern"
        if matched
        else "no processor pattern matched (not wrapped)"
    )
    return result


def main():
    use_utf8_io()
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
