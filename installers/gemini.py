"""Gemini CLI specific installer logic for Token-Saver."""

import os

from .common import (
    IS_WINDOWS,
    SHARED_FILES,
    home,
    install_files,
    stamp_version,
    uninstall_dir,
)

GEMINI_FILES = [
    *SHARED_FILES,
    "gemini/gemini-extension.json",
    "gemini/hooks.json",
    "gemini/hook_aftertool.py",
]


def _extension_dir():
    """Return where we install the extension files for Gemini CLI."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "gemini", "extensions", "token-saver")
    return os.path.join(home(), ".gemini", "extensions", "token-saver")


def install(use_symlink=False):
    """Install Token-Saver for Gemini CLI."""
    target_dir = _extension_dir()
    print(f"\n--- Gemini CLI ({target_dir}) ---")
    install_files(target_dir, GEMINI_FILES, use_symlink)
    stamp_version(target_dir, ["gemini/gemini-extension.json"])


def uninstall():
    """Uninstall Token-Saver from Gemini CLI."""
    print("\n--- Gemini CLI ---")
    uninstall_dir(_extension_dir())
