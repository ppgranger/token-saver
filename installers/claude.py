"""Claude Code specific installer logic for Token-Saver."""

import json
import os

from .common import (
    HOOK_MARKER,
    IS_WINDOWS,
    SHARED_FILES,
    home,
    install_files,
    python_cmd,
    stamp_version,
    uninstall_dir,
)

CLAUDE_FILES = [
    *SHARED_FILES,
    "claude/plugin.json",
    "claude/hook_pretool.py",
    "claude/wrap.py",
]


def _settings_dir():
    """Return Claude Code settings directory."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "claude")
    return os.path.join(home(), ".claude")


def _plugin_dir():
    """Return where we install the plugin files for Claude Code."""
    return os.path.join(_settings_dir(), "plugins", "token-saver")


def _settings_path():
    """Return path to Claude Code settings.json."""
    return os.path.join(_settings_dir(), "settings.json")


def _hook_belongs_to_us(hook_entry):
    """Check if a hook entry (new format) belongs to token-saver."""
    for h in hook_entry.get("hooks", []):
        cmd = h.get("command", "")
        if HOOK_MARKER in cmd or "hook_pretool" in cmd or "hook_session" in cmd:
            return True
    return False


def _register_hooks(target_dir):
    """Register hooks in Claude Code's settings.json using the new matcher format."""
    settings_path = _settings_path()
    python = python_cmd()

    hooks_script_pretool = f"{python} {target_dir}/claude/hook_pretool.py"
    hooks_script_session = f"{python} {target_dir}/src/hook_session.py"

    # On Windows, use backslashes in paths
    if IS_WINDOWS:
        hooks_script_pretool = hooks_script_pretool.replace("/", "\\")
        hooks_script_session = hooks_script_session.replace("/", "\\")

    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)

    hooks = settings.setdefault("hooks", {})

    # --- PreToolUse hook (matcher as string, hooks as array) ---
    pretool_list = hooks.setdefault("PreToolUse", [])

    # Remove any old-format or existing token-saver entries
    pretool_list[:] = [
        entry
        for entry in pretool_list
        if not _hook_belongs_to_us(entry)
        and not (
            HOOK_MARKER in str(entry.get("command", ""))
            or "hook_pretool" in str(entry.get("command", ""))
        )
    ]

    pretool_list.append(
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": hooks_script_pretool,
                    "timeout": 5000,
                }
            ],
        }
    )
    print("  REGISTERED PreToolUse hook in settings.json")

    # --- SessionStart hook (new format, no matcher needed) ---
    session_list = hooks.setdefault("SessionStart", [])

    # Remove any old-format or existing token-saver entries
    session_list[:] = [
        entry
        for entry in session_list
        if not _hook_belongs_to_us(entry)
        and not (
            HOOK_MARKER in str(entry.get("command", ""))
            or "hook_session" in str(entry.get("command", ""))
        )
    ]

    session_list.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": hooks_script_session,
                    "timeout": 3000,
                }
            ],
        }
    )
    print("  REGISTERED SessionStart hook in settings.json")

    # Ensure directory exists
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def _unregister_hooks():
    """Remove token-saver hooks from Claude Code settings.json."""
    settings_path = _settings_path()
    if not os.path.exists(settings_path):
        print("  settings.json not found, nothing to clean")
        return

    with open(settings_path) as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    changed = False

    for event in ("PreToolUse", "SessionStart"):
        if event not in hooks:
            continue
        original_len = len(hooks[event])
        hooks[event] = [
            entry
            for entry in hooks[event]
            if not _hook_belongs_to_us(entry)
            and HOOK_MARKER not in str(entry.get("command", ""))
            and "hook_pretool" not in str(entry.get("command", ""))
            and "hook_session" not in str(entry.get("command", ""))
        ]
        if len(hooks[event]) != original_len:
            changed = True
        if not hooks[event]:
            del hooks[event]

    if not hooks:
        settings.pop("hooks", None)

    if changed:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        print("  REMOVED hooks from settings.json")
    else:
        print("  No token-saver hooks found in settings.json")


def install(use_symlink=False):
    """Install Token-Saver for Claude Code."""
    target_dir = _plugin_dir()
    print(f"\n--- Claude Code ({target_dir}) ---")
    install_files(target_dir, CLAUDE_FILES, use_symlink)
    stamp_version(target_dir, ["claude/plugin.json"])
    _register_hooks(target_dir)


def uninstall():
    """Uninstall Token-Saver from Claude Code."""
    print("\n--- Claude Code ---")
    _unregister_hooks()
    uninstall_dir(_plugin_dir())
