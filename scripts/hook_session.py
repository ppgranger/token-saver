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

"""SessionStart hook entry point for Claude Code plugin.

Delegates to src/hook_session.py. This wrapper exists because:
- Claude Code plugin hooks reference scripts/ via ${CLAUDE_PLUGIN_ROOT}
- Antigravity CLI references src/hook_session.py via ${extensionPath}
- Both paths must work independently
"""

import os
import sys

# Add plugin root to path so src/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Installed hook entry points locate their sibling package before imports.
# pylint: disable=wrong-import-position
import src.hook_session

if __name__ == "__main__":
    src.hook_session.main()
