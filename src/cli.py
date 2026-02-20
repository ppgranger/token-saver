"""CLI entry point for token-saver: version, stats, update."""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
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
        latest = _fetch_latest_version()
    except Exception as e:
        print(f"Failed to check for updates: {e}")
        sys.exit(1)

    if _parse_version(latest) <= _parse_version(__version__):
        print(f"Already up to date (v{__version__}).")
        return

    print(f"Update available: v{__version__} -> v{latest}")

    git_dir = os.path.join(repo_dir, ".git")
    if os.path.isdir(git_dir):
        _update_via_git(repo_dir, latest)
    else:
        _update_via_tarball(repo_dir, latest)

    # Re-run installer
    print("Re-running installer...")
    install_script = os.path.join(repo_dir, "install.py")
    subprocess.run(  # noqa: S603
        [sys.executable, install_script, "--target", "both"],
        check=True,
    )

    print(f"Update complete! Now running v{latest}.")


def _update_via_git(repo_dir, version):
    """Update using git fetch + checkout."""
    print("Updating via git...")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "fetch", "--tags"],  # noqa: S607
        check=True,
    )
    # Try tag with 'v' prefix first, then without
    for tag in (f"v{version}", version):
        result = subprocess.run(  # noqa: S603
            ["git", "-C", repo_dir, "checkout", tag],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            print(f"Checked out {tag}")
            return
    print(f"Warning: could not checkout tag for v{version}, pulling latest main")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "pull", "origin", "main"],  # noqa: S607
        check=True,
    )


def _update_via_tarball(repo_dir, version):
    """Update by downloading and extracting release tarball."""
    print("Downloading update...")
    url = f"https://github.com/ppgranger/token-saving/archive/refs/tags/v{version}.tar.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "token-saver"})  # noqa: S310

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball_path = os.path.join(tmpdir, "release.tar.gz")
        with (
            urllib.request.urlopen(req, timeout=30) as resp,  # noqa: S310
            open(tarball_path, "wb") as f,
        ):
            f.write(resp.read())

        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(tmpdir)  # noqa: S202

        # Find the extracted directory (e.g., token-saving-1.2.0/)
        extracted = [
            d
            for d in os.listdir(tmpdir)
            if os.path.isdir(os.path.join(tmpdir, d)) and d != "release.tar.gz"
        ]
        if not extracted:
            print("Error: could not find extracted release directory")
            sys.exit(1)

        src_dir = os.path.join(tmpdir, extracted[0])

        # Overlay files into repo_dir
        for item in os.listdir(src_dir):
            s = os.path.join(src_dir, item)
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
