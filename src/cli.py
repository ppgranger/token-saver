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

"""CLI entry point for token-saver: version, stats, update, benchmark."""

import argparse
import json as json_mod
import os
import subprocess
import sys
import time

import src
from src import console
from src import updater


def _repo_dir():
    """Return the repository root directory (parent of src/).

    Returns:
        Absolute path containing the running src package.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Keep the historical helper names callable without coupling update execution
# to the CLI module. Patch updater operations through their owning module.
# pylint: disable=invalid-name
_is_marketplace_managed = updater.is_marketplace_managed
_is_within_directory = updater.is_within_directory
_safe_extractall = updater.safe_extractall
_detect_installed_targets = updater.detect_installed_targets
_update_via_git = updater.update_via_git
_update_via_tarball = updater.update_via_tarball
# pylint: enable=invalid-name


def cmd_version(unused_args):  # noqa: ARG001 — argparse callback contract
    """Print current version.

    Args:
        unused_args: Unused namespace required by the command-handler API.
    """
    print(f"token-saver v{src.__version__}")


def cmd_stats(args):
    """Display savings statistics, delegating to src/stats.py.

    Args:
        args: Parsed command-line arguments for this subcommand.
    """
    # Defer this adapter dependency until its command or hook is used.
    # pylint: disable-next=import-outside-toplevel
    from src import stats  # noqa: PLC0415

    stats.main(["--json"] if args.json else [])


def cmd_update(unused_args):  # noqa: ARG001 — argparse callback contract
    """Delegate release application and local refresh to the update adapter.

    Args:
        unused_args: Unused namespace required by the command-handler API.

    Raises:
        subprocess.CalledProcessError: Updating or refreshing the installation
            fails.
    """
    updater.update(_repo_dir())


def cmd_benchmark(args):
    """Benchmark compression on a real or dry-run command.

    Args:
        args: Parsed command-line arguments for this subcommand.
    """
    # Defer this adapter dependency until its command or hook is used.
    # pylint: disable-next=import-outside-toplevel
    from src import config  # noqa: PLC0415

    # Defer this adapter dependency until its command or hook is used.
    # pylint: disable-next=import-outside-toplevel
    from src import diffstat  # noqa: PLC0415

    # Defer this adapter dependency until its command or hook is used.
    # pylint: disable-next=import-outside-toplevel
    from src import engine as engine_lib  # noqa: PLC0415

    command = args.command_str
    chars_per_token = config.get("chars_per_token")
    engine = engine_lib.CompressionEngine()

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
            print(
                "(no execution — use without --dry-run to measure compression)"
            )
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
            # See scripts/wrap.py: locale decoding is a Windows crash waiting
            # to happen, and losing the command is worse than a mangled char.
            encoding="utf-8",
            errors="replace",
            timeout=config.get("wrap_timeout"),
            check=False,
        )
        exec_elapsed = time.monotonic() - exec_start

        raw_output = result.stdout
        if result.stderr:
            raw_output += result.stderr

    compress_start = time.monotonic()
    compressed, processor_name, was_compressed = engine.compress(
        command, raw_output
    )
    compress_elapsed = time.monotonic() - compress_start

    orig_chars = len(raw_output)
    comp_chars = len(compressed)
    orig_tokens = (
        max(1, round(orig_chars / chars_per_token)) if orig_chars > 0 else 0
    )
    comp_tokens = (
        max(1, round(comp_chars / chars_per_token)) if comp_chars > 0 else 0
    )
    savings_pct = (
        (orig_chars - comp_chars) / orig_chars * 100 if orig_chars > 0 else 0
    )

    show_removed = getattr(args, "show_removed", False)
    diff_summary = (
        diffstat.summarize(raw_output, compressed) if show_removed else None
    )

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
        print(
            f"Time:        {exec_elapsed:.2f}s (exec) + "
            f"{compress_elapsed:.3f}s (compress)"
        )
        if diff_summary is not None:
            print(diffstat.format_summary(diff_summary))


def cmd_explain(args):
    """Explain how a command would be routed: processor, regex, exclusion.

    Args:
        args: Parsed command-line arguments for this subcommand.
    """
    # Load routing and processor discovery only for the explanation command.
    # pylint: disable=import-outside-toplevel
    from src import chain_utils  # noqa: PLC0415
    from src import command_policy  # noqa: PLC0415
    from src import engine as engine_lib  # noqa: PLC0415

    # pylint: enable=import-outside-toplevel

    command = args.command_str
    decision = command_policy.explain_decision(command)

    # Which processor would handle the primary command (first match wins).
    primary = chain_utils.extract_primary_command(command)
    engine = engine_lib.CompressionEngine()
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
    # Defer this adapter dependency until its command or hook is used.
    # pylint: disable-next=import-outside-toplevel
    from src import delta_cli  # noqa: PLC0415

    # Keep optional CLI adapters out of library imports.
    # pylint: disable-next=import-outside-toplevel
    from src import quality_cli  # noqa: PLC0415

    console.use_utf8_io()
    parser = argparse.ArgumentParser(
        prog="token-saver",
        description="Token-Saver: compress verbose tool outputs to save tokens",
    )
    subparsers = parser.add_subparsers(dest="command")
    quality_cli.add_quality_parsers(subparsers)
    delta_cli.add_delta_parsers(subparsers)

    # version
    subparsers.add_parser("version", help="Show current version")

    # stats
    stats_parser = subparsers.add_parser(
        "stats", help="Show savings statistics"
    )
    stats_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # update
    subparsers.add_parser("update", help="Check for and apply updates")

    # benchmark
    bench_parser = subparsers.add_parser(
        "benchmark", help="Benchmark compression on a command"
    )
    bench_parser.add_argument(
        "command_str", help="Command to benchmark (quote if needed)"
    )
    bench_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    bench_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show processor match without executing",
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
    explain_parser.add_argument(
        "command_str", help="Command to explain (quote if needed)"
    )
    explain_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
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
    handler = getattr(args, "handler", None) or commands[args.command]
    handler(args)


if __name__ == "__main__":
    main()
