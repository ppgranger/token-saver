"""Claude Code specific installer logic for Token-Saver.

v2.0: Registers as a native Claude Code plugin instead of injecting hooks
into settings.json. The manual installer registers the GitHub repo as a
known marketplace and writes installed_plugins.json in the v2 format that
Claude Code expects.
"""

import json
import os
import shutil

from .common import (
    HOOK_MARKER,
    IS_WINDOWS,
    SHARED_FILES,
    home,
    install_files,
    stamp_version,
    uninstall_dir,
)

CLAUDE_FILES = [
    *SHARED_FILES,
    # Plugin metadata
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    # Hooks (native plugin format — Claude Code reads these automatically)
    "hooks/hooks.json",
    # Scripts
    "scripts/__init__.py",
    "scripts/hook_pretool.py",
    "scripts/wrap.py",
    "scripts/hook_session.py",
    # Skills and commands
    "skills/token-saver-config/SKILL.md",
    "commands/token-saver-stats.md",
    # Plugin instructions
    "CLAUDE.md",
]

_MARKETPLACE_NAME = "token-saver-marketplace"
_PLUGIN_KEY = f"token-saver@{_MARKETPLACE_NAME}"
_GITHUB_REPO = "ppgranger/token-saver"


def _settings_dir():
    """Return Claude Code settings directory."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "claude")
    return os.path.join(home(), ".claude")


def _plugin_dir():
    """Return the OLD v1.x plugin install directory (for migration/cleanup only)."""
    return os.path.join(_settings_dir(), "plugins", "token-saver")


def _plugin_cache_dir(version):
    """Return the Claude Code plugin cache directory for token-saver.

    Claude Code stores plugins at .../cache/<marketplace>/<plugin>/<version>/.
    """
    return os.path.join(
        _settings_dir(),
        "plugins",
        "cache",
        _MARKETPLACE_NAME,
        "token-saver",
        version,
    )


def _settings_path():
    """Return path to Claude Code settings.json."""
    return os.path.join(_settings_dir(), "settings.json")


def _installed_plugins_path():
    """Return path to Claude Code's installed plugins registry."""
    return os.path.join(_settings_dir(), "plugins", "installed_plugins.json")


def _known_marketplaces_path():
    """Return path to Claude Code's known marketplaces registry."""
    return os.path.join(_settings_dir(), "plugins", "known_marketplaces.json")


def _hook_belongs_to_us(hook_entry):
    """Check if a hook entry (new format) belongs to token-saver."""
    for h in hook_entry.get("hooks", []):
        cmd = h.get("command", "")
        if HOOK_MARKER in cmd or "hook_pretool" in cmd or "hook_session" in cmd:
            return True
    return False


def _read_version():
    """Read the current token-saver version from src/__init__.py."""
    from .common import _read_version as _rv  # noqa: PLC0415

    return _rv()


def _iso_now():
    """Return current UTC time in ISO 8601 format."""
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _register_plugin(target_dir, version):
    """Register token-saver as a native Claude Code plugin.

    Registers the GitHub repo as a known marketplace, writes the plugin
    entry in installed_plugins.json (v2 format), and enables it in
    settings.json.
    """
    plugins_dir = os.path.join(_settings_dir(), "plugins")
    os.makedirs(plugins_dir, exist_ok=True)
    now = _iso_now()

    # --- 1. Register marketplace in known_marketplaces.json ---
    km_path = _known_marketplaces_path()
    known = {}
    if os.path.exists(km_path):
        try:
            with open(km_path) as f:
                known = json.load(f)
        except (json.JSONDecodeError, ValueError):
            known = {}

    known[_MARKETPLACE_NAME] = {
        "source": {
            "source": "github",
            "repo": _GITHUB_REPO,
        },
        "installLocation": target_dir,
        "lastUpdated": now,
    }

    with open(km_path, "w") as f:
        json.dump(known, f, indent=2)
        f.write("\n")
    print("  REGISTERED marketplace in known_marketplaces.json")

    # --- 2. Update installed_plugins.json (v2 format) ---
    plugins_path = _installed_plugins_path()

    registry = {"version": 2, "plugins": {}}
    if os.path.exists(plugins_path):
        try:
            with open(plugins_path) as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("version") == 2:
                registry = data
        except (json.JSONDecodeError, ValueError):
            pass

    registry["plugins"][_PLUGIN_KEY] = [
        {
            "scope": "user",
            "installPath": target_dir,
            "version": version,
            "installedAt": now,
            "lastUpdated": now,
        },
    ]

    with open(plugins_path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")
    print("  REGISTERED in installed_plugins.json")

    # --- 3. Enable in settings.json ---
    settings_path = _settings_path()
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)

    enabled = settings.setdefault("enabledPlugins", {})
    enabled[_PLUGIN_KEY] = True

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("  ENABLED in settings.json (enabledPlugins)")


def _unregister_plugin():
    """Unregister token-saver from Claude Code's plugin system.

    Removes from known_marketplaces.json, installed_plugins.json,
    disables in enabledPlugins, and cleans up any legacy v1.x hooks.
    """
    # --- 1. Remove from known_marketplaces.json ---
    km_path = _known_marketplaces_path()
    if os.path.exists(km_path):
        try:
            with open(km_path) as f:
                known = json.load(f)
            if _MARKETPLACE_NAME in known:
                del known[_MARKETPLACE_NAME]
                with open(km_path, "w") as f:
                    json.dump(known, f, indent=2)
                    f.write("\n")
                print("  REMOVED from known_marketplaces.json")
        except (json.JSONDecodeError, ValueError):
            pass

    # --- 2. Remove from installed_plugins.json (handle both v1 and v2 formats) ---
    plugins_path = _installed_plugins_path()
    if os.path.exists(plugins_path):
        try:
            with open(plugins_path) as f:
                data = json.load(f)

            changed = False
            if isinstance(data, dict) and data.get("version") == 2:
                # v2 format: plugins is a dict keyed by "name@marketplace"
                plugins = data.get("plugins", {})
                for key in list(plugins):
                    if "token-saver" in key:
                        del plugins[key]
                        changed = True
            elif isinstance(data, list):
                # v1 format (our old code): array of plugin objects
                original_len = len(data)
                data = [p for p in data if p.get("name") != "token-saver"]
                changed = len(data) != original_len

            if changed:
                with open(plugins_path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                print("  REMOVED from installed_plugins.json")
        except (json.JSONDecodeError, ValueError):
            pass

    # --- 3. Remove from enabledPlugins + clean legacy hooks from settings.json ---
    settings_path = _settings_path()
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)

        changed = False

        # Remove from enabledPlugins
        enabled = settings.get("enabledPlugins", {})
        for key in list(enabled):
            if "token-saver" in key:
                del enabled[key]
                changed = True
        if not enabled and "enabledPlugins" in settings:
            del settings["enabledPlugins"]

        # Clean up any legacy v1.x hooks (backward compat)
        hooks = settings.get("hooks", {})
        for event in list(hooks):
            if not isinstance(hooks[event], list):
                continue
            original_len = len(hooks[event])
            hooks[event] = [entry for entry in hooks[event] if not _hook_belongs_to_us(entry)]
            if len(hooks[event]) != original_len:
                changed = True
            if not hooks[event]:
                del hooks[event]
        if not hooks and "hooks" in settings:
            del settings["hooks"]

        if changed:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")
            print("  REMOVED from settings.json")


def _migrate_from_v1():
    """Detect and clean up v1.x hook-injection installation.

    v1.x injected hooks directly into ~/.claude/settings.json with absolute
    paths to claude/hook_pretool.py and src/hook_session.py. v2.0 registers
    as a native plugin instead. Remove old hooks and old directories.

    Returns True if migration was performed.
    """
    had_changes = False

    # 1. Clean old hooks from settings.json
    settings_path = _settings_path()
    if os.path.exists(settings_path):
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except (json.JSONDecodeError, ValueError):
            settings = {}

        hooks = settings.get("hooks", {})
        for event in list(hooks):
            if not isinstance(hooks[event], list):
                continue
            original_len = len(hooks[event])
            hooks[event] = [entry for entry in hooks[event] if not _hook_belongs_to_us(entry)]
            if len(hooks[event]) != original_len:
                had_changes = True
            if not hooks[event]:
                del hooks[event]

        if had_changes:
            if not hooks:
                settings.pop("hooks", None)
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")
            print("  MIGRATED: removed v1.x hooks from settings.json")

    # 2. Remove old plugin dir at ~/.claude/plugins/token-saver/ (v1 location)
    old_plugin_dir = _plugin_dir()
    if os.path.isdir(old_plugin_dir):
        old_claude_subdir = os.path.join(old_plugin_dir, "claude")
        has_old_format = os.path.isdir(old_claude_subdir) or not os.path.isdir(
            os.path.join(old_plugin_dir, ".claude-plugin")
        )
        if has_old_format:
            shutil.rmtree(old_plugin_dir)
            print(f"  REMOVED legacy v1 plugin directory: {old_plugin_dir}")
            had_changes = True

    # 3. Remove old cache at .../cache/token-saver-marketplace/token-saver/
    #    (our earlier v2 attempt that didn't include version in path)
    old_cache = os.path.join(
        _settings_dir(),
        "plugins",
        "cache",
        _MARKETPLACE_NAME,
        "token-saver",
    )
    if os.path.isdir(old_cache):
        # Check if this is the flat (no-version) layout by looking for
        # .claude-plugin directly inside it (the versioned layout would
        # have a version subdirectory containing .claude-plugin instead)
        has_flat_layout = os.path.isdir(os.path.join(old_cache, ".claude-plugin")) and not any(
            os.path.isdir(os.path.join(old_cache, d, ".claude-plugin"))
            for d in os.listdir(old_cache)
            if os.path.isdir(os.path.join(old_cache, d))
        )
        if has_flat_layout:
            shutil.rmtree(old_cache)
            print(f"  REMOVED old flat cache: {old_cache}")
            had_changes = True

    return had_changes


def install(use_symlink=False):
    """Install Token-Saver for Claude Code as a native plugin.

    This produces the same result as:
      /plugin marketplace add ppgranger/token-saver
      /plugin install token-saver

    Files are installed to the plugin cache directory (with version in the
    path), the GitHub repo is registered as a known marketplace, and the
    plugin is added to installed_plugins.json (v2 format) and enabledPlugins.
    """
    # 1. Migrate from v1.x (clean old hooks, old directories)
    _migrate_from_v1()

    # 2. Install files to the versioned plugin cache directory
    version = _read_version()
    target_dir = _plugin_cache_dir(version)
    print(f"\n--- Claude Code ({target_dir}) ---")
    install_files(target_dir, CLAUDE_FILES, use_symlink)

    # 3. Stamp version in BOTH plugin.json and marketplace.json
    stamp_version(
        target_dir,
        [
            ".claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
        ],
    )

    # 4. Register marketplace + plugin
    _register_plugin(target_dir, version)

    print("  Plugin registered. Restart Claude Code, then /plugin to manage.")


def uninstall():
    """Uninstall Token-Saver from Claude Code."""
    print("\n--- Claude Code ---")
    _unregister_plugin()

    # Remove entire marketplace cache directory (all versions)
    cache_root = os.path.join(
        _settings_dir(),
        "plugins",
        "cache",
        _MARKETPLACE_NAME,
    )
    if os.path.isdir(cache_root):
        uninstall_dir(cache_root)

    # Also remove old v1 location if it still exists
    old_dir = _plugin_dir()
    if os.path.isdir(old_dir):
        uninstall_dir(old_dir)
