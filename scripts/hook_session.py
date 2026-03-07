#!/usr/bin/env python3
"""SessionStart hook entry point for Claude Code plugin.

Delegates to src/hook_session.py. This wrapper exists because:
- Claude Code plugin hooks reference scripts/ via ${CLAUDE_PLUGIN_ROOT}
- Gemini CLI references src/hook_session.py via ${extensionPath}
- Both paths must work independently
"""

import os
import sys

# Add plugin root to path so src/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hook_session import main

if __name__ == "__main__":
    main()
