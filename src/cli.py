"""CLI entry point for token-saver: version, stats, update, benchmark."""

import argparse
import json as json_mod
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

from src import __version__
from src.version_check import _fetch_latest_version, _parse_version


def _repo_dir():
    """Return the repository root directory (parent of src/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_marketplace_managed(repo_dir: str) -> bool:
    """True if this install lives under a Claude Code plugin marketplace cache.

    Marketplace-managed installs live at
    ``~/.claude/plugins/cache/<marketplace>/token-saver`` (or the Windows
    %APPDATA% equivalent).  Self-updating those via git/tarball fights the
    marketplace, so ``token-saver update`` should defer to ``/plugin update``.
    """
    parts = [p.lower() for p in os.path.normpath(os.path.abspath(repo_dir)).split(os.sep)]
    return any(
        parts[i] == "plugins" and parts[i + 1] == "cache" for i in range(len(parts) - 1)
    )


def _is_within_directory(directory: str, target: str) -> bool:
    """True if ``target`` resolves to a path inside ``directory``."""
    abs_dir = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    return os.path.commonpath([abs_dir]) == os.path.commonpath([abs_dir, abs_target])


def _safe_extractall(tar: "tarfile.TarFile", dest: str) -> None:
    """Extract a tarball, rejecting members that escape ``dest``.

    Prefers the stdlib ``data`` filter (Python 3.12+), which blocks path
    traversal, absolute paths, and special files.  Falls back to manual member
    validation on older interpreters.
    """
    try:
        tar.extractall(dest, filter="data")
        return
    except TypeError:
        pass  # `filter` kwarg unavailable (< 3.12) — validate manually

    for member in tar.getmembers():
        member_path = os.path.join(dest, member.name)
        if not _is_within_directory(dest, member_path):
            raise RuntimeError(f"Unsafe path in release tarball: {member.name!r}")
        if member.issym() or member.islnk():
            link_target = os.path.join(dest, os.path.dirname(member.name), member.linkname)
            if not _is_within_directory(dest, link_target):
                raise RuntimeError(f"Unsafe link in release tarball: {member.name!r}")
    tar.extractall(dest)  # noqa: S202


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
    """Check for updates, then always refresh the local install.

    Remote fetch is best-effort: if it fails or matches the local version,
    we still re-run the installer so the Claude/Gemini plugin caches stay
    in sync with the source files on disk.
    """
    repo_dir = _repo_dir()
    print(f"token-saver v{__version__}")

    if _is_marketplace_managed(repo_dir):
        print(
            "This install is managed by the Claude Code plugin marketplace.\n"
            "Run '/plugin update token-saver' from within Claude Code to update."
        )
        return

    print("Checking for updates...")
    latest = None
    try:
        latest = _fetch_latest_version(timeout=10)
    except urllib.error.HTTPError as e:
        print(f"Could not check remote: HTTP {e.code} (continuing with local refresh)")
    except Exception as e:
        print(f"Could not check remote: {e} (continuing with local refresh)")

    is_newer = False
    if latest is not None:
        try:
            is_newer = _parse_version(latest) > _parse_version(__version__)
        except (ValueError, TypeError):
            print(f"Could not compare versions: local={__version__}, remote={latest}")

    if is_newer:
        print(f"Update available: v{__version__} -> v{latest}")
        git_dir = os.path.join(repo_dir, ".git")
        if os.path.isdir(git_dir):
            _update_via_git(repo_dir, latest)
        else:
            _update_via_tarball(repo_dir, latest)
    elif latest is not None:
        print(f"Already on v{__version__} (no remote update).")

    targets = _detect_installed_targets()
    print(f"Refreshing plugin install for: {targets}...")
    install_script = os.path.join(repo_dir, "install.py")
    subprocess.run(  # noqa: S603
        [sys.executable, install_script, "--target", targets],
        check=True,
    )

    final_version = latest if is_newer else __version__
    print(f"Done. Running v{final_version}.")


def _detect_installed_targets():
    """Detect which platforms are currently installed and return the --target value."""
    h = os.path.expanduser("~")
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.join(h, "AppData", "Roaming"))
        claude_old = os.path.join(appdata, "claude", "plugins", "token-saver")
        claude_cache = os.path.join(
            appdata, "claude", "plugins", "cache", "token-saver-marketplace", "token-saver"
        )
        gemini_dir = os.path.join(appdata, "gemini", "extensions", "token-saver")
    else:
        claude_old = os.path.join(h, ".claude", "plugins", "token-saver")
        claude_cache = os.path.join(
            h, ".claude", "plugins", "cache", "token-saver-marketplace", "token-saver"
        )
        gemini_dir = os.path.join(h, ".gemini", "extensions", "token-saver")

    claude_installed = os.path.isdir(claude_old) or os.path.isdir(claude_cache)
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
            _safe_extractall(tar, tmpdir)

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
            "scripts",
            ".claude-plugin",
            "hooks",
            "skills",
            "commands",
            "gemini",
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


def cmd_benchmark(args):
    """Benchmark compression on a real or dry-run command."""
    from src import config  # noqa: PLC0415
    from src.diffstat import format_summary, summarize  # noqa: PLC0415
    from src.engine import CompressionEngine  # noqa: PLC0415

    command = args.command_str
    chars_per_token = config.get("chars_per_token")
    engine = CompressionEngine()

    if args.dry_run:
        # Dry-run: show which processor would handle it, without executing
        processor_name = "none"
        for p in engine.processors:
            if p.can_handle(command):
                processor_name = p.name
                break

        if args.format == "json":
            print(
                json_mod.dumps(
                    {
                        "command": command,
                        "processor": processor_name,
                        "dry_run": True,
                    }
                )
            )
        else:
            print()
            print("Token-Saver Benchmark (dry-run)")
            print("=" * 40)
            print(f"Command:     {command}")
            print(f"Processor:   {processor_name}")
            print("(no execution — use without --dry-run to measure compression)")
        return

    if getattr(args, "stdin", False):
        # Compress pre-captured output piped on stdin; command is used only for
        # processor routing, not executed.
        raw_output = sys.stdin.read()
        exec_elapsed = 0.0
    else:
        # Execute the command and measure
        exec_start = time.monotonic()
        result = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=config.get("wrap_timeout"),
            check=False,
        )
        exec_elapsed = time.monotonic() - exec_start

        raw_output = result.stdout
        if result.stderr:
            raw_output += result.stderr

    compress_start = time.monotonic()
    compressed, processor_name, was_compressed = engine.compress(command, raw_output)
    compress_elapsed = time.monotonic() - compress_start

    orig_chars = len(raw_output)
    comp_chars = len(compressed)
    orig_tokens = max(1, round(orig_chars / chars_per_token)) if orig_chars > 0 else 0
    comp_tokens = max(1, round(comp_chars / chars_per_token)) if comp_chars > 0 else 0
    savings_pct = (orig_chars - comp_chars) / orig_chars * 100 if orig_chars > 0 else 0

    show_removed = getattr(args, "show_removed", False)
    diff_summary = summarize(raw_output, compressed) if show_removed else None

    if args.format == "json":
        payload = {
            "command": command,
            "processor": processor_name,
            "was_compressed": was_compressed,
            "original_chars": orig_chars,
            "compressed_chars": comp_chars,
            "original_tokens": orig_tokens,
            "compressed_tokens": comp_tokens,
            "savings_percent": round(savings_pct, 1),
            "exec_time_s": round(exec_elapsed, 3),
            "compress_time_s": round(compress_elapsed, 3),
        }
        if diff_summary is not None:
            payload["removed"] = diff_summary
        print(json_mod.dumps(payload))
    else:
        print()
        print("Token-Saver Benchmark")
        print("=" * 40)
        print(f"Command:     {command}")
        print(f"Processor:   {processor_name}")
        print(f"Original:    {orig_chars:,} chars (~{orig_tokens:,} tokens)")
        print(f"Compressed:  {comp_chars:,} chars (~{comp_tokens:,} tokens)")
        print(f"Savings:     {savings_pct:.1f}%")
        print(f"Time:        {exec_elapsed:.2f}s (exec) + {compress_elapsed:.3f}s (compress)")
        if diff_summary is not None:
            print(format_summary(diff_summary))


def cmd_explain(args):
    """Explain how a command would be routed: processor, regex, exclusion."""
    from scripts.hook_pretool import explain_decision  # noqa: PLC0415
    from src.chain_utils import extract_primary_command  # noqa: PLC0415
    from src.engine import CompressionEngine  # noqa: PLC0415

    command = args.command_str
    decision = explain_decision(command)

    # Which processor would handle the primary command (first match wins).
    primary = extract_primary_command(command)
    engine = CompressionEngine()
    processor_name = "none"
    processor_patterns: list[str] = []
    for p in engine.processors:
        if p.can_handle(primary):
            processor_name = p.name
            processor_patterns = list(p.hook_patterns)
            break

    if args.format == "json":
        print(
            json_mod.dumps(
                {
                    "command": command,
                    "primary_command": primary,
                    "compressible": decision["compressible"],
                    "reason": decision["reason"],
                    "excluded_by": decision["excluded_by"],
                    "matched_patterns": decision["matched_patterns"],
                    "is_chain": decision["is_chain"],
                    "processor": processor_name,
                    "processor_hook_patterns": processor_patterns,
                }
            )
        )
        return

    print()
    print("Token-Saver Explain")
    print("=" * 40)
    print(f"Command:      {command}")
    if primary != command:
        print(f"Primary:      {primary}")
    print(f"Compressible: {'yes' if decision['compressible'] else 'no'}")
    print(f"Reason:       {decision['reason']}")
    if decision["excluded_by"]:
        print(f"Excluded by:  {decision['excluded_by']}")
    print(f"Processor:    {processor_name}")
    if decision["matched_patterns"]:
        print("Matched patterns:")
        for pat in decision["matched_patterns"]:
            print(f"  - {pat}")
    if processor_patterns and not decision["matched_patterns"]:
        print("Processor hook patterns:")
        for pat in processor_patterns:
            print(f"  - {pat}")


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

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark compression on a command")
    bench_parser.add_argument("command_str", help="Command to benchmark (quote if needed)")
    bench_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    bench_parser.add_argument(
        "--dry-run", action="store_true", help="Show processor match without executing"
    )
    bench_parser.add_argument(
        "--show-removed",
        action="store_true",
        help="Show a line/byte breakdown of what compression removed",
    )
    bench_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Compress output piped on stdin instead of executing the command",
    )

    # explain
    explain_parser = subparsers.add_parser(
        "explain", help="Explain how a command would be routed/excluded"
    )
    explain_parser.add_argument("command_str", help="Command to explain (quote if needed)")
    explain_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "version": cmd_version,
        "stats": cmd_stats,
        "update": cmd_update,
        "benchmark": cmd_benchmark,
        "explain": cmd_explain,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
