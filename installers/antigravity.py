"""Antigravity CLI specific installer logic for Token-Saver."""

import os

from .common import (
    IS_WINDOWS,
    SHARED_FILES,
    home,
    install_files,
    stamp_version,
    uninstall_dir,
)

ANTIGRAVITY_FILES = [
    *SHARED_FILES,
    "antigravity/antigravity-plugin.json",
    "antigravity/hooks.json",
    "antigravity/hook_aftertool.py",
]


def _plugin_dir():
    """Return where we install the plugin files for Antigravity CLI."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "gemini", "antigravity-cli", "plugins", "token-saver")
    return os.path.join(home(), ".gemini", "antigravity-cli", "plugins", "token-saver")


def install(use_symlink=False):
    """Install Token-Saver for Antigravity CLI."""
    target_dir = _plugin_dir()
    print(f"\n--- Antigravity CLI ({target_dir}) ---")
    install_files(target_dir, ANTIGRAVITY_FILES, use_symlink)
    stamp_version(target_dir, ["antigravity/antigravity-plugin.json"])


def uninstall():
    """Uninstall Token-Saver from Antigravity CLI."""
    print("\n--- Antigravity CLI ---")
    uninstall_dir(_plugin_dir())
