#!/usr/bin/env python3
"""AfterTool hook for Antigravity CLI.

Reads JSON from stdin, compresses tool output, replaces it via deny+reason.
"""

import json
import os
import sys

# Ensure the plugin root is importable (antigravity/ -> plugin root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import core
from src.platforms import Platform, get_command, get_tool_output


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    platform = Platform.ANTIGRAVITY_CLI

    command = get_command(input_data, platform) or ""
    output = get_tool_output(input_data, platform)

    if not output:
        sys.exit(0)

    # Shared gate: skip commands Claude wouldn't wrap either (sudo, complex
    # pipelines, interactive tools, etc.).
    if not core.should_compress(command):
        json.dump({}, sys.stdout)
        sys.exit(0)

    result = core.compress(command, output)

    if not result.was_compressed:
        # No significant compression — let the original output through
        json.dump({}, sys.stdout)
        sys.exit(0)

    core.record_result(result, command, "antigravity_cli")

    json.dump({"decision": "deny", "reason": result.compressed}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
