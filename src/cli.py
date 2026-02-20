"""CLI entry point for token-saver: version, stats, update."""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

from src import __version__
from src.version_check import _fetch_latest_version, _parse_version


def _repo_dir():
    """Return the repository root directory (parent of src/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cmd_version(_args):
    """Print current version."""
    print(f"token-saver v{__version__}")


def cmd_stats(args):
    """Display savings statistics, delegating to src/stats.py."""
    from src.stats import main as stats_main  # noqa: PLC0415

    # Patch sys.argv so stats.main() sees --json if passed
    original_argv = sys.argv
    sys.argv = ["stats"]
    if args.json:
        sys.argv.append("--json")
    try:
        stats_main()
    finally:
        sys.argv = original_argv


def cmd_update(_args):
    """Check for updates and apply if available."""
    repo_dir = _repo_dir()
    print(f"token-saver v{__version__}")

    print("Checking for updates...")
    try:
        latest = _fetch_latest_version(timeout=10)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("No releases found on GitHub. Is the repository public with releases?")
        else:
            print(f"Failed to check for updates: HTTP {e.code}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to check for updates: {e}")
        sys.exit(1)

    try:
        is_newer = _parse_version(latest) > _parse_version(__version__)
    except (ValueError, TypeError):
        print(f"Could not compare versions: local={__version__}, remote={latest}")
        sys.exit(1)

    if not is_newer:
        print(f"Already up to date (v{__version__}).")
        return

    print(f"Update available: v{__version__} -> v{latest}")

    git_dir = os.path.join(repo_dir, ".git")
    if os.path.isdir(git_dir):
        _update_via_git(repo_dir, latest)
    else:
        _update_via_tarball(repo_dir, latest)

    # Re-run installer — detect which platforms are currently installed
    targets = _detect_installed_targets()
    print(f"Re-running installer for: {targets}...")
    install_script = os.path.join(repo_dir, "install.py")
    subprocess.run(  # noqa: S603
        [sys.executable, install_script, "--target", targets],
        check=True,
    )

    print(f"Update complete! Now running v{latest}.")


def _detect_installed_targets():
    """Detect which platforms are currently installed and return the --target value."""
    h = os.path.expanduser("~")
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.join(h, "AppData", "Roaming"))
        claude_dir = os.path.join(appdata, "claude", "plugins", "token-saver")
        gemini_dir = os.path.join(appdata, "gemini", "extensions", "token-saver")
    else:
        claude_dir = os.path.join(h, ".claude", "plugins", "token-saver")
        gemini_dir = os.path.join(h, ".gemini", "extensions", "token-saver")

    claude_installed = os.path.isdir(claude_dir)
    gemini_installed = os.path.isdir(gemini_dir)

    if claude_installed and gemini_installed:
        return "both"
    if gemini_installed:
        return "gemini"
    # Default to claude (most common, and safe even if dir was just cleaned)
    return "claude"


def _update_via_git(repo_dir, version):
    """Update using git fetch + merge tag into current branch."""
    print("Updating via git...")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "fetch", "--tags", "origin"],  # noqa: S607
        check=True,
    )
    # Try to merge the tag into the current branch (avoids detached HEAD)
    for tag in (f"v{version}", version):
        result = subprocess.run(  # noqa: S603
            ["git", "-C", repo_dir, "merge", tag, "--ff-only"],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            print(f"Merged {tag} into current branch.")
            return
    # Fallback: pull latest main
    print(f"Warning: could not fast-forward to v{version}, pulling latest main")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "pull", "origin", "main"],  # noqa: S607
        check=True,
    )


def _update_via_tarball(repo_dir, version):
    """Update by downloading and extracting release tarball."""
    print("Downloading update...")

    # Try both tag formats: v1.2.0 and 1.2.0 (mirrors _update_via_git behavior)
    urls = [
        f"https://github.com/ppgranger/token-saver/archive/refs/tags/v{version}.tar.gz",
        f"https://github.com/ppgranger/token-saver/archive/refs/tags/{version}.tar.gz",
    ]

    tarball_data = None
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "token-saver"})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                tarball_data = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise

    if tarball_data is None:
        print(f"Error: could not download release v{version} from GitHub")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball_path = os.path.join(tmpdir, "release.tar.gz")
        with open(tarball_path, "wb") as f:
            f.write(tarball_data)

        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(tmpdir)  # noqa: S202

        # Find the extracted directory (e.g., token-saver-1.2.0/)
        extracted = [
            d
            for d in os.listdir(tmpdir)
            if os.path.isdir(os.path.join(tmpdir, d)) and d != "release.tar.gz"
        ]
        if not extracted:
            print("Error: could not find extracted release directory")
            sys.exit(1)

        src_dir = os.path.join(tmpdir, extracted[0])

        # Overlay known source directories only (preserve .git, local config, etc.)
        overlay_items = (
            "src",
            "installers",
            "claude",
            "gemini",
            "bin",
            "install.py",
            "pyproject.toml",
        )
        for item in overlay_items:
            s = os.path.join(src_dir, item)
            if not os.path.exists(s):
                continue
            d = os.path.join(repo_dir, item)
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
        print("Files updated from tarball.")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="token-saver",
        description="Token-Saver: compress verbose tool outputs to save tokens",
    )
    subparsers = parser.add_subparsers(dest="command")

    # version
    subparsers.add_parser("version", help="Show current version")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show savings statistics")
    stats_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # update
    subparsers.add_parser("update", help="Check for and apply updates")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "version": cmd_version,
        "stats": cmd_stats,
        "update": cmd_update,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
