"""Shared constants, file lists, and utility functions for Token-Saver installers."""

import json
import os
import platform
import re
import shutil
import stat

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
    "src/version_check.py",
    "src/cli.py",
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


def _read_version():
    """Read __version__ from src/__init__.py using regex."""
    init_path = os.path.join(EXTENSION_DIR, "src", "__init__.py")
    with open(init_path) as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError("Could not find __version__ in src/__init__.py")
    return match.group(1)


def stamp_version(target_dir, manifest_paths):
    """Stamp the current version into JSON manifest files.

    Skips files that are symlinks (development mode).

    Args:
        target_dir: Root directory of the installed plugin/extension.
        manifest_paths: List of relative paths to JSON manifests to stamp.
    """
    version = _read_version()
    for rel_path in manifest_paths:
        manifest = os.path.join(target_dir, rel_path)
        if not os.path.exists(manifest) or os.path.islink(manifest):
            continue
        with open(manifest) as f:
            data = json.load(f)
        data["version"] = version
        with open(manifest, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"  STAMPED version {version} in {rel_path}")


def _cli_install_dir():
    """Return the directory for CLI executable installation."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "token-saver", "bin")
    return os.path.join(home(), ".local", "bin")


def install_cli(use_symlink=False):
    """Install the token-saver CLI command to PATH.

    Args:
        use_symlink: If True, create a symlink instead of copying.
    """
    install_dir = _cli_install_dir()
    os.makedirs(install_dir, exist_ok=True)

    if IS_WINDOWS:
        src_name = "token-saver.cmd"
        src_path = os.path.join(EXTENSION_DIR, "bin", src_name)
        dst_path = os.path.join(install_dir, src_name)
        # Also install the Python script the .cmd calls
        py_src = os.path.join(EXTENSION_DIR, "bin", "token-saver")
        py_dst = os.path.join(install_dir, "token-saver")
    else:
        src_name = "token-saver"
        src_path = os.path.join(EXTENSION_DIR, "bin", src_name)
        dst_path = os.path.join(install_dir, src_name)

    if use_symlink:
        if os.path.exists(dst_path) or os.path.islink(dst_path):
            os.remove(dst_path)
        os.symlink(src_path, dst_path)
        print(f"  LINK {src_name} -> {dst_path}")
    else:
        shutil.copy2(src_path, dst_path)
        # Ensure executable on Unix
        if not IS_WINDOWS:
            st = os.stat(dst_path)
            os.chmod(dst_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  COPY {src_name} -> {dst_path}")

    if IS_WINDOWS:
        if not use_symlink:
            shutil.copy2(py_src, py_dst)
        else:
            if os.path.exists(py_dst) or os.path.islink(py_dst):
                os.remove(py_dst)
            os.symlink(py_src, py_dst)

    # Check if install_dir is in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    if install_dir not in path_dirs:
        print(f"\n  NOTE: {install_dir} is not in your PATH.")
        if IS_WINDOWS:
            print(f'  Add it: setx PATH "%PATH%;{install_dir}"')
        else:
            print(f'  Add it: export PATH="{install_dir}:$PATH"')
            print("  (Add the above line to your ~/.bashrc or ~/.zshrc)")


def uninstall_cli():
    """Remove the token-saver CLI command."""
    install_dir = _cli_install_dir()
    names = ["token-saver"]
    if IS_WINDOWS:
        names.append("token-saver.cmd")
    for name in names:
        path = os.path.join(install_dir, name)
        if os.path.exists(path) or os.path.islink(path):
            os.remove(path)
            print(f"  REMOVED {path}")
