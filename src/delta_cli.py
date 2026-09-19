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

"""Read and remove opt-in Delta snapshots without executing commands."""

from __future__ import annotations

import sqlite3
import sys
from typing import TYPE_CHECKING

from src import delta
from src import delta_redaction

if TYPE_CHECKING:
    import argparse


def cmd_show(args: argparse.Namespace) -> None:
    """Print a retained sanitized snapshot or one exact diagnostic.

    Args:
        args: Parsed run_id and optional diagnostic identifier.

    Raises:
        SystemExit: Status 1 for expired/missing data; 2 for invalid input or
            unavailable storage. Errors never echo captured content.
    """
    try:
        with delta.open_store() as store:
            payload = store.get(args.run_id)
        if payload is None:
            print("Delta snapshot missing or expired.", file=sys.stderr)
            raise SystemExit(1)
        snapshot, exit_code = delta.restore(payload)
        if args.diagnostic is None:
            output = delta.render(snapshot, exit_code=exit_code)
        else:
            matches = [
                item.detail
                for item in snapshot.diagnostics
                if item.identifier == args.diagnostic
            ]
            if not matches:
                print("Diagnostic not in this snapshot.", file=sys.stderr)
                raise SystemExit(1)
            output = matches[0]
        print(delta_redaction.sanitize(output), end="")
    except (OSError, ValueError, sqlite3.Error):
        print("Cannot read Delta snapshot safely.", file=sys.stderr)
        raise SystemExit(2) from None


def cmd_clear(args: argparse.Namespace) -> None:
    """Remove all retained Delta snapshots and reset comparison baselines.

    Args:
        args: Unused namespace supplied by the command dispatcher.

    Raises:
        SystemExit: Status 2 when the store cannot be opened safely.
    """
    del args
    try:
        with delta.open_store() as store:
            count = store.clear()
    except (OSError, ValueError, sqlite3.Error):
        print("Cannot clear Delta snapshots safely.", file=sys.stderr)
        raise SystemExit(2) from None
    print(f"Cleared {count} Delta snapshot(s).")


def add_delta_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register the Delta detail and retention commands on the main CLI.

    Args:
        subparsers: Main argparse subcommand collection.
    """
    parser = subparsers.add_parser(
        "delta", help="Inspect or clear retained Delta diagnostics"
    )
    commands = parser.add_subparsers(dest="delta_command", required=True)
    show = commands.add_parser(
        "show", help="Read sanitized details without rerunning a command"
    )
    show.add_argument("run_id", help="Opaque ID printed by Delta")
    show.add_argument(
        "--diagnostic", help="Read only the diagnostic with this exact ID"
    )
    show.set_defaults(handler=cmd_show)
    clear = commands.add_parser(
        "clear", help="Delete all Delta snapshots and reset comparisons"
    )
    clear.set_defaults(handler=cmd_clear)
