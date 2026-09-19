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

"""Apply release updates and refresh local platform installations.

This adapter owns optional release lookup, Git/archive updates, progress output,
and the installer subprocess. It accepts an explicit source directory and has
no dependency on CLI parsing or process-global argument mutation. Importing it
does not download, install, or otherwise change the user's profile.
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

import src
from src import version_check


def is_marketplace_managed(repo_dir: str) -> bool:
    """True if this install lives under a Claude Code plugin marketplace cache.

    Marketplace-managed installs live at
    ``~/.claude/plugins/cache/<marketplace>/token-saver`` (or the Windows
    %APPDATA% equivalent).  Self-updating those via git/tarball fights the
    marketplace, so ``token-saver update`` should defer to ``/plugin update``.

    Args:
        repo_dir: Root of the checkout or installed source tree to inspect or
            update.

    Returns:
        Whether the path contains a Claude plugin-cache directory layout.
    """
    parts = [
        p.lower()
        for p in os.path.normpath(os.path.abspath(repo_dir)).split(os.sep)
    ]
    return any(
        parts[i] == "plugins" and parts[i + 1] == "cache"
        for i in range(len(parts) - 1)
    )


def is_within_directory(directory: str, target: str) -> bool:
    """True if ``target`` resolves to a path inside ``directory``.

    Args:
        directory: Containing directory used as the extraction boundary.
        target: Candidate path to compare against that boundary.

    Returns:
        Whether the absolute candidate path lies within the extraction
        directory.
    """
    abs_dir = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    return os.path.commonpath([abs_dir]) == os.path.commonpath(
        [abs_dir, abs_target]
    )


def safe_extractall(tar: "tarfile.TarFile", dest: str) -> None:
    """Extract a tarball, rejecting members that escape ``dest``.

    Prefers the stdlib ``data`` filter (Python 3.12+), which blocks path
    traversal, absolute paths, and special files.  Falls back to manual member
    validation on older interpreters.

    Args:
        tar: Open tar archive containing the release files.
        dest: Directory within which archive entries must remain.

    Raises:
        RuntimeError: An archive member or link escapes the destination.
        tarfile.TarError: Archive data or a standard-library extraction filter
            rejects a member.
        OSError: An extracted file cannot be written.
    """
    try:
        tar.extractall(dest, filter="data")
        return
    except TypeError:
        pass  # `filter` kwarg unavailable (< 3.12) — validate manually

    for member in tar.getmembers():
        member_path = os.path.join(dest, member.name)
        if not is_within_directory(dest, member_path):
            raise RuntimeError(
                f"Unsafe path in release tarball: {member.name!r}"
            )
        if member.issym() or member.islnk():
            link_target = os.path.join(
                dest, os.path.dirname(member.name), member.linkname
            )
            if not is_within_directory(dest, link_target):
                raise RuntimeError(
                    f"Unsafe link in release tarball: {member.name!r}"
                )
    tar.extractall(dest)  # noqa: S202


def update(repo_dir: str) -> None:
    """Check for updates, then always refresh the local install.

    Remote fetch is best-effort: if it fails or matches the local version, we
    still re-run the installer so the Claude/Antigravity plugin caches stay in
    sync with the source files on disk.

    Args:
        repo_dir: Explicit checkout or installed tree to update and refresh.

    Raises:
        subprocess.CalledProcessError: Updating or refreshing the installation
            fails.
    """
    print(f"token-saver v{src.__version__}")

    if is_marketplace_managed(repo_dir):
        print(
            "This install is managed by the Claude Code plugin marketplace.\n"
            "Run '/plugin update token-saver' from within Claude Code "
            "to update."
        )
        return

    print("Checking for updates...")
    latest = None
    try:
        # Reuse the established release-check helper API.
        # pylint: disable-next=protected-access
        latest = version_check._fetch_latest_version(timeout=10)
    except urllib.error.HTTPError as e:
        print(
            f"Could not check remote: HTTP {e.code} "
            "(continuing with local refresh)"
        )
    # Isolate an optional release lookup without exposing exception text,
    # which may contain credentials or private connection details.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        print("Could not check remote (continuing with local refresh)")

    is_newer = False
    if latest is not None:
        try:
            # Keep CLI and hook comparisons on the same version parser.
            # pylint: disable=protected-access
            is_newer = version_check._parse_version(
                latest
            ) > version_check._parse_version(src.__version__)
            # pylint: enable=protected-access
        except (ValueError, TypeError):
            print(
                f"Could not compare versions: local={src.__version__}, "
                f"remote={latest}"
            )

    if is_newer:
        print(f"Update available: v{src.__version__} -> v{latest}")
        git_dir = os.path.join(repo_dir, ".git")
        if os.path.isdir(git_dir):
            update_via_git(repo_dir, latest)
        else:
            update_via_tarball(repo_dir, latest)
    elif latest is not None:
        print(f"Already on v{src.__version__} (no remote update).")

    targets = detect_installed_targets()
    print(f"Refreshing plugin install for: {targets}...")
    install_script = os.path.join(repo_dir, "install.py")
    subprocess.run(  # noqa: S603
        [sys.executable, install_script, "--target", targets],
        check=True,
    )

    final_version = latest if is_newer else src.__version__
    print(f"Done. Running v{final_version}.")


def detect_installed_targets():
    """Detect the installer target for the currently installed platforms.

    Returns:
        The installer target string: claude, antigravity, or both.
    """
    h = os.path.expanduser("~")
    if os.name == "nt":
        appdata = os.environ.get(
            "APPDATA", os.path.join(h, "AppData", "Roaming")
        )
        claude_old = os.path.join(appdata, "claude", "plugins", "token-saver")
        claude_cache = os.path.join(
            appdata,
            "claude",
            "plugins",
            "cache",
            "token-saver-marketplace",
            "token-saver",
        )
        antigravity_dir = os.path.join(
            appdata, "gemini", "antigravity-cli", "plugins", "token-saver"
        )
    else:
        claude_old = os.path.join(h, ".claude", "plugins", "token-saver")
        claude_cache = os.path.join(
            h,
            ".claude",
            "plugins",
            "cache",
            "token-saver-marketplace",
            "token-saver",
        )
        antigravity_dir = os.path.join(
            h, ".gemini", "antigravity-cli", "plugins", "token-saver"
        )

    claude_installed = os.path.isdir(claude_old) or os.path.isdir(claude_cache)
    antigravity_installed = os.path.isdir(antigravity_dir)

    if claude_installed and antigravity_installed:
        return "both"
    if antigravity_installed:
        return "antigravity"
    # Default to claude (most common, and safe even if dir was just cleaned)
    return "claude"


def update_via_git(repo_dir, version):
    """Update using git fetch + merge tag into current branch.

    Args:
        repo_dir: Root of the checkout or installed source tree to inspect or
            update.
        version: Release version used for the tag or installation path.

    Raises:
        subprocess.CalledProcessError: Fetching tags or the fallback pull fails.
    """
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


def update_via_tarball(repo_dir, version):
    """Update by downloading and extracting release tarball.

    Args:
        repo_dir: Root of the checkout or installed source tree to inspect or
            update.
        version: Release version used for the tag or installation path.
    """
    print("Downloading update...")

    # Try both tag formats: v1.2.0 and 1.2.0 (mirrors update_via_git behavior)
    urls = [
        "https://github.com/ppgranger/token-saver/archive/refs/tags/"
        f"v{version}.tar.gz",
        "https://github.com/ppgranger/token-saver/archive/refs/tags/"
        f"{version}.tar.gz",
    ]

    tarball_data = None
    for url in urls:
        req = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "token-saver"}
        )
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
            safe_extractall(tar, tmpdir)

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

        # Overlay known source directories only (preserve .git, local config,
        # etc.)
        overlay_items = (
            "src",
            "installers",
            "scripts",
            ".claude-plugin",
            "hooks",
            "skills",
            "commands",
            "antigravity",
            "bin",
            "install.py",
            "pyproject.toml",
            "CLAUDE.md",
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

        # Clean up legacy claude/ directory from v1.x
        legacy_claude = os.path.join(repo_dir, "claude")
        if os.path.isdir(legacy_claude):
            shutil.rmtree(legacy_claude)
            print("Removed legacy claude/ directory.")

        print("Files updated from tarball.")
