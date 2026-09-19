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

"""CLI adapters for stdin compression and offline quality-contract replay."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src import config
from src import engine
from src import evaluation
from src import replay


def non_negative_int(value: str) -> int:
    """Parse an argparse value as a nonnegative integer.

    Args:
        value: Raw command-line argument to parse.

    Returns:
        The parsed nonnegative integer.

    Raises:
        argparse.ArgumentTypeError: The parsed integer is negative.
        ValueError: The argument is not an integer.
    """
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return number


def _read_stdin() -> str:
    """Read UTF-8 stdin within the configured capture size limit.

    Returns:
        Decoded input text without modifying its contents.

    Raises:
        OSError: Standard input cannot be read.
        UnicodeDecodeError: Standard input is not valid UTF-8.
        ValueError: The size limit is invalid or standard input exceeds it.
    """
    limit = config.get("max_output_bytes")
    # Reject bool and numeric subclasses before using the value as a byte limit.
    # pylint: disable-next=unidiomatic-typecheck
    if type(limit) is not int or limit <= 0:
        raise ValueError("max_output_bytes must be a positive integer")
    data = sys.stdin.buffer.read(limit + 1)
    if len(data) > limit:
        raise ValueError("captured output exceeds max_output_bytes")
    return data.decode("utf-8")


def cmd_compress(args: argparse.Namespace) -> None:
    """Compress stdin and write the requested text or JSON representation.

    Args:
        args: Parsed compress options, including command_str, exit_code,
            max_tokens, and format. The command label is never executed.

    Raises:
        SystemExit: Status 1 when the budget is exceeded, or status 2 when
            input or configuration validation fails. Budget failures retain
            the complete compressor output.
    """
    try:
        result = evaluation.evaluate(
            engine.CompressionEngine(),
            args.command_str,
            _read_stdin(),
            exit_code=args.exit_code,
            chars_per_token=config.get("chars_per_token"),
            policy=evaluation.QualityPolicy(max_tokens=args.max_tokens),
        )
    except (OSError, ValueError) as error:
        print(f"token-saver compress: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    if args.format == "json":
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "output": result.compressed,
                    **result.report(),
                }
            )
        )
    else:
        sys.stdout.write(result.compressed)
        if result.violations:
            print(
                "token-saver: estimated output "
                f"{result.compressed_tokens} tokens "
                f"exceeds budget {args.max_tokens}; output retained",
                file=sys.stderr,
            )
    if result.violations:
        raise SystemExit(1)


def cmd_replay(args: argparse.Namespace) -> None:
    """Write a replay report and expose quality violations as a CI exit status.

    Args:
        args: Parsed replay options containing manifest and format.

    Raises:
        SystemExit: Status 1 when quality checks fail, or status 2 when the
            manifest, captures, or configuration cannot be read or validated.
    """
    try:
        report = replay.replay(
            pathlib.Path(args.manifest),
            engine.CompressionEngine(),
            chars_per_token=config.get("chars_per_token"),
            max_input_bytes=config.get("max_output_bytes"),
        )
    except (OSError, ValueError) as error:
        print(f"token-saver replay: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    if args.format == "json":
        print(json.dumps(report))
    else:
        print("Token-Saver Quality Replay")
        print("Token counts are estimates, not model-tokenizer counts.")
        for case in report["cases"]:
            status = "PASS" if case["passed"] else "FAIL"
            # JSON encoding prevents terminal control sequences in case names.
            name = json.dumps(case["name"], ensure_ascii=True)
            print(
                f"{status} {name}: ~{case['original_tokens']} -> "
                f"~{case['compressed_tokens']} tokens "
                f"({case['savings_percent']}% saved)"
            )
            if case["violations"]:
                print("  " + ", ".join(case["violations"]))
        totals = report["totals"]
        print(
            f"{totals['passed']}/{totals['cases']} cases passed; "
            f"~{totals['compressed_tokens']} total output tokens"
        )
        if totals["violations"]:
            print("FAIL max_total_tokens")
    if not report["passed"]:
        raise SystemExit(1)


def add_quality_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Add compress and replay subcommands to the main argument parser.

    Args:
        subparsers: Existing argparse subcommand collection to extend in place.
    """
    compress_parser = subparsers.add_parser(
        "compress",
        help="Compress UTF-8 stdin without executing the command label",
    )
    compress_parser.add_argument(
        "command_str", help="Command label for processor routing only"
    )
    compress_parser.add_argument(
        "--format", choices=["text", "json"], default="text"
    )
    compress_parser.add_argument(
        "--exit-code", type=int, help="Exit status of the captured command"
    )
    compress_parser.add_argument(
        "--max-tokens", type=non_negative_int, help="Estimated output budget"
    )
    compress_parser.set_defaults(handler=cmd_compress)
    replay_parser = subparsers.add_parser(
        "replay",
        help=(
            "Check captured outputs against quality contracts and token budgets"
        ),
    )
    replay_parser.add_argument(
        "manifest", help="Path to a version 1 JSON replay manifest"
    )
    replay_parser.add_argument(
        "--format", choices=["text", "json"], default="text"
    )
    replay_parser.set_defaults(handler=cmd_replay)
