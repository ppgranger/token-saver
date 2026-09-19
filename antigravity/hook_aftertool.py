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

"""AfterTool hook for Antigravity CLI.

Reads JSON from stdin, compresses tool output, replaces it via deny+reason.
"""

import json
import os
import sys

# Ensure the plugin root is importable (antigravity/ -> plugin root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Installed entrypoints must establish the package root first.
# pylint: disable=wrong-import-position
from src import console
from src import core
from src import platforms

# pylint: enable=wrong-import-position


def main():
    """Read one host payload and emit replacement output when compressed."""
    console.use_utf8_io()
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    platform = platforms.Platform.ANTIGRAVITY_CLI

    command = platforms.get_command(input_data, platform) or ""
    output = platforms.get_tool_output(input_data, platform)

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
