#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PreToolUse hook for Claude Code.

Reads JSON from stdin, rewrites compressible commands to go through wrap.py.
Uses shlex.quote() to prevent shell injection when rewriting.
"""

import json
import logging
import os
import shlex
import sys

# Ensure the extension root is importable (scripts/ -> plugin root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Installed hooks must locate their sibling packages before importing them.
# pylint: disable=wrong-import-position
import src.console
from src import command_policy

# --- Debug logging (writes to data_dir/hook.log when TOKEN_SAVER_DEBUG=true)
# ---
_log = logging.getLogger("token-saver.hook_pretool")
_log.setLevel(logging.DEBUG)
_debug = os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes")
if _debug:
    import src

    _log_dir = src.data_dir()
    os.makedirs(_log_dir, exist_ok=True)
    _handler = logging.FileHandler(os.path.join(_log_dir, "hook.log"))
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    _log.addHandler(_handler)
else:
    _log.addHandler(logging.NullHandler())


# Build patterns from processor registry (auto-discovered)
def _load_compressible_patterns() -> list[str]:
    """Import hook_patterns from the processor registry."""
    # Add extension root to path so we can import the src package
    this_dir = os.path.dirname(os.path.abspath(__file__))
    extension_root = os.path.dirname(this_dir)
    _log.debug("this_dir=%s, extension_root=%s", this_dir, extension_root)
    if extension_root not in sys.path:
        sys.path.insert(0, extension_root)
    # Load plugins inside the failure boundary so failures cannot block Bash.
    # pylint: disable=import-outside-toplevel
    from src import processors  # noqa: PLC0415

    patterns = processors.collect_hook_patterns()
    _log.debug("Loaded %d compressible patterns", len(patterns))
    return patterns


def _available_patterns() -> list[str]:
    """Return discovered patterns, or disable compression on plugin failure."""
    try:
        return _load_compressible_patterns()
    except Exception:  # pylint: disable=broad-exception-caught
        # A broken user plugin must not prevent Bash commands from running.
        _log.warning(
            "Failed to load compressible patterns — compression disabled"
        )
        return []


# Historical names remain available to integrations and existing tests.
# pylint: disable=invalid-name
_compile_patterns = command_policy.compile_patterns
_policy = command_policy.CommandPolicy(_available_patterns())
COMPRESSIBLE_PATTERNS = _policy.pattern_sources
COMPILED_PATTERNS = _policy.compiled_patterns
EXCLUDED_PATTERNS = command_policy.EXCLUDED_PATTERNS
COMPILED_EXCLUDED = command_policy.COMPILED_EXCLUDED
is_compressible = _policy.is_compressible
explain_decision = _policy.explain_decision
is_destructive = command_policy.is_destructive
# Retain historical helper imports without making policy internals public.
# pylint: disable=protected-access
_normalize_cmd = command_policy._normalize_cmd
_has_unquoted_construct = command_policy._has_unquoted_construct
_has_output_redirection = command_policy._has_output_redirection
_is_segment_safe = command_policy._is_segment_safe
# pylint: enable=protected-access
# pylint: enable=invalid-name


def main():
    """Read one hook request and emit its command-rewrite decision as JSON."""
    src.console.use_utf8_io()
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

    if is_destructive(command):
        # Compressible, but irreversible enough that we must not remove the
        # user's normal permission check by auto-approving it — see
        # is_destructive()'s docstring.  Emit nothing so Claude Code falls
        # through to its own allow/ask/deny rules for this command exactly
        # as if token-saver were not installed.
        _log.debug("Destructive, declining to auto-approve: %r", command[:200])
        sys.exit(0)

    # Build path to wrap.py (same directory)
    wrap_py = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "wrap.py"
    )
    if not os.path.isfile(wrap_py):
        _log.warning("wrap.py not found at %s", wrap_py)
        sys.exit(0)  # Fail open — don't break the command

    # Pass Claude Code's session_id so all compressions in the same Claude
    # session share one tracker session.  We embed it as an env var prefix in
    # the rewritten command so it propagates to the wrap.py subprocess.
    cc_session = input_data.get("session_id", "")

    # Rewrite: pass the original command as a single quoted argument to avoid
    # injection
    python = "python" if os.name == "nt" else "python3"
    session_prefix = (
        f"TOKEN_SAVER_SESSION={shlex.quote(cc_session)} " if cc_session else ""
    )
    new_command = (
        f"{session_prefix}{python} {shlex.quote(wrap_py)} "
        f"{shlex.quote(command)}"
    )
    _log.debug(
        "Rewriting: %r -> %r (session=%s)", command, new_command, cc_session
    )

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
