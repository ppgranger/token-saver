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

"""Platform detection and I/O format abstraction."""

import enum


class Platform(enum.Enum):
    """Supported host hook protocols and an unrecognized-platform sentinel."""

    CLAUDE_CODE = "claude_code"
    ANTIGRAVITY_CLI = "antigravity_cli"
    UNKNOWN = "unknown"


def detect_platform(input_data: dict) -> Platform:
    """Detect platform based on hook event name or structure.

    Args:
        input_data: Decoded host hook payload.

    Returns:
        The recognized host platform, or Platform.UNKNOWN.
    """
    event = input_data.get("hook_event_name", "")
    if event in ("PreToolUse", "PostToolUse", "SessionStart"):
        return Platform.CLAUDE_CODE
    if event in ("BeforeTool", "AfterTool"):
        return Platform.ANTIGRAVITY_CLI
    # Fallback heuristics
    if "tool_input" in input_data and "tool_response" in input_data:
        return Platform.ANTIGRAVITY_CLI
    if "tool_name" in input_data:
        return Platform.CLAUDE_CODE
    return Platform.UNKNOWN


def get_command(input_data: dict, platform: Platform) -> str | None:
    """Extract the command string from hook input.

    Args:
        input_data: Decoded host hook payload.
        platform: Host platform whose hook payload convention should be used.

    Returns:
        The command converted to text, or None when no command is present.
    """
    if platform == Platform.CLAUDE_CODE:
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command")
        return str(cmd) if cmd is not None else None
    if platform == Platform.ANTIGRAVITY_CLI:
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command") or tool_input.get("cmd")
        return str(cmd) if cmd is not None else None
    return None


def get_tool_output(input_data: dict, platform: Platform) -> str | None:
    """Extract tool output from hook input (Antigravity AfterTool only).

    Args:
        input_data: Decoded host hook payload.
        platform: Host platform whose hook payload convention should be used.

    Returns:
        Captured output as text, or None for absent or unsupported output.
    """
    if platform == Platform.ANTIGRAVITY_CLI:
        response = input_data.get("tool_response", {})
        content = response.get("llmContent", response.get("output", ""))
        if isinstance(content, list):
            return "\n".join(str(c) for c in content)
        return str(content) if content else None
    return None


def format_pretool_rewrite(
    new_command: str, permission_decision: str = "allow"
) -> dict:
    """Format a PreToolUse response that rewrites the command (Claude Code).

    Args:
        new_command: Replacement shell command passed to Claude Code.
        permission_decision: Permission decision included in the hook response.

    Returns:
        A Claude Code hookSpecificOutput mapping.
    """
    return {
        "hookSpecificOutput": {
            "permissionDecision": permission_decision,
            "updatedInput": {"command": new_command},
        }
    }


def format_aftertool_deny(compressed_output: str) -> dict:
    """Format an AfterTool response that replaces output (Antigravity CLI).

    Args:
        compressed_output: Replacement tool output sent to Antigravity.

    Returns:
        An Antigravity replacement response with decision and reason fields.
    """
    return {"decision": "deny", "reason": compressed_output}
