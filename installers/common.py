"""Shared constants, file lists, and utility functions for Token-Saver installers."""

import os
import platform
import shutil

EXTENSION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = platform.system() == "Windows"
HOOK_MARKER = "token-saver"

SHARED_FILES = [
    "src/__init__.py",
    "src/config.py",
    "src/platforms.py",
    "src/engine.py",
    "src/hook_session.py",
    "src/tracker.py",
    "src/stats.py",
    "src/processors/__init__.py",
    "src/processors/base.py",
    "src/processors/git.py",
    "src/processors/test_output.py",
    "src/processors/build_output.py",
    "src/processors/lint_output.py",
    "src/processors/network.py",
    "src/processors/docker.py",
    "src/processors/kubectl.py",
    "src/processors/terraform.py",
    "src/processors/env.py",
    "src/processors/search.py",
    "src/processors/system_info.py",
    "src/processors/package_list.py",
    "src/processors/file_listing.py",
    "src/processors/file_content.py",
    "src/processors/generic.py",
]


def home():
    """Return user home directory, works on all platforms."""
    return os.path.expanduser("~")


def python_cmd():
    """Return python command appropriate for the platform."""
    if IS_WINDOWS:
        return "python"
    return "python3"


def token_saver_data_dir():
    """Return path to ~/.token-saver (or platform equivalent) for DB and config."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "token-saver")
    return os.path.join(home(), ".token-saver")


def install_files(target_dir, file_list, use_symlink=False):
    """Copy or symlink extension files to the target directory."""
    os.makedirs(target_dir, exist_ok=True)

    for rel_path in file_list:
        src = os.path.join(EXTENSION_DIR, rel_path)
        dst = os.path.join(target_dir, rel_path)

        if not os.path.exists(src):
            print(f"  WARNING: Source file missing: {src}")
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)

        if use_symlink:
            if os.path.exists(dst) or os.path.islink(dst):
                os.remove(dst)
            os.symlink(src, dst)
            print(f"  LINK {rel_path}")
        else:
            shutil.copy2(src, dst)
            print(f"  COPY {rel_path}")

    # Fix hooks.json for Windows: replace python3 with python
    hooks_path = os.path.join(target_dir, "gemini", "hooks.json")
    if IS_WINDOWS and os.path.exists(hooks_path) and not os.path.islink(hooks_path):
        with open(hooks_path) as f:
            content = f.read()
        content = content.replace("python3 ", "python ")
        with open(hooks_path, "w") as f:
            f.write(content)
        print("  PATCHED hooks.json for Windows python")


def uninstall_dir(target_dir):
    """Remove installed plugin/extension directory."""
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
        print(f"  REMOVED {target_dir}")
    else:
        print(f"  NOT FOUND {target_dir} (already removed)")


def uninstall_data_dir():
    """Remove token-saver data directory (~/.token-saver) with DB and config."""
    data_dir = token_saver_data_dir()
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
        print(f"  REMOVED {data_dir}")
    else:
        print(f"  NOT FOUND {data_dir} (already removed)")
