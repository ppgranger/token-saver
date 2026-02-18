#!/usr/bin/env python3
"""AfterTool hook for Gemini CLI.

Reads JSON from stdin, compresses tool output, replaces it via deny+reason.
"""

import json
import os
import sys

# Ensure the extension root is importable (gemini/ -> extension/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import CompressionEngine
from src.platforms import Platform, get_command, get_tool_output
from src.tracker import SavingsTracker


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    platform = Platform.GEMINI_CLI

    command = get_command(input_data, platform) or ""
    output = get_tool_output(input_data, platform)

    if not output:
        sys.exit(0)

    engine = CompressionEngine()
    compressed, processor_name, was_compressed = engine.compress(command, output)

    if not was_compressed:
        # No significant compression — let the original output through
        json.dump({}, sys.stdout)
        sys.exit(0)

    # Track savings
    try:
        tracker = SavingsTracker()
        tracker.record_saving(
            command=command,
            processor=processor_name,
            original_size=len(output),
            compressed_size=len(compressed),
            platform="gemini_cli",
        )
        tracker.close()
    except Exception:  # noqa: S110
        pass

    result = {
        "decision": "deny",
        "reason": compressed,
    }
    json.dump(result, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
