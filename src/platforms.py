"""Platform detection and I/O format abstraction."""

from enum import Enum


class Platform(Enum):
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"
    UNKNOWN = "unknown"


def detect_platform(input_data: dict) -> Platform:
    """Detect platform based on hook event name or structure."""
    event = input_data.get("hook_event_name", "")
    if event in ("PreToolUse", "PostToolUse", "SessionStart"):
        return Platform.CLAUDE_CODE
    if event in ("BeforeTool", "AfterTool"):
        return Platform.GEMINI_CLI
    # Fallback heuristics
    if "tool_input" in input_data and "tool_response" in input_data:
        return Platform.GEMINI_CLI
    if "tool_name" in input_data:
        return Platform.CLAUDE_CODE
    return Platform.UNKNOWN


def get_command(input_data: dict, platform: Platform) -> str | None:
    """Extract the command string from hook input."""
    if platform == Platform.CLAUDE_CODE:
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command")
        return str(cmd) if cmd is not None else None
    if platform == Platform.GEMINI_CLI:
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command") or tool_input.get("cmd")
        return str(cmd) if cmd is not None else None
    return None


def get_tool_output(input_data: dict, platform: Platform) -> str | None:
    """Extract tool output from hook input (Gemini AfterTool only)."""
    if platform == Platform.GEMINI_CLI:
        response = input_data.get("tool_response", {})
        content = response.get("llmContent", response.get("output", ""))
        if isinstance(content, list):
            return "\n".join(str(c) for c in content)
        return str(content) if content else None
    return None


def format_pretool_rewrite(new_command: str, permission_decision: str = "allow") -> dict:
    """Format a PreToolUse response that rewrites the command (Claude Code)."""
    return {
        "hookSpecificOutput": {
            "permissionDecision": permission_decision,
            "updatedInput": {"command": new_command},
        }
    }


def format_aftertool_deny(compressed_output: str) -> dict:
    """Format an AfterTool response that replaces output (Gemini CLI)."""
    return {"decision": "deny", "reason": compressed_output}
