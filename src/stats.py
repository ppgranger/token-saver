#!/usr/bin/env python3
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

"""Display token-saver savings statistics.

Usage:
    python3 stats.py              # Human-readable summary
    python3 stats.py --json       # JSON output for scripting
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Installed entrypoints must establish the package root first.
# pylint: disable=wrong-import-position
from src import config
from src import console
from src import stats_formatting
from src import tracker as tracker_lib

# pylint: enable=wrong-import-position

# ── ANSI escape codes ──────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
WHITE = "\033[97m"
BOLD_GREEN = "\033[1;32m"
BOLD_WHITE = "\033[1;97m"
BOLD_YELLOW = "\033[1;33m"

WIDTH = 50


def _chars_to_tokens(n: int) -> int:
    """Estimate token count from character count.

    Args:
        n: Nonnegative count to format or convert.

    Returns:
        A rounded token estimate using the configured characters-per-token
        ratio.
    """
    return stats_formatting.estimate_tokens(n, config.get("chars_per_token"))


def _format_tokens(n: int) -> str:
    """Human-readable token count.

    Args:
        n: Nonnegative count to format or convert.

    Returns:
        Compact token-count text with K or M suffixes when appropriate.
    """
    if n < 1_000:
        return f"{n}"
    if n < 1_000_000:
        return f"{n / 1_000:.1f}K"
    return f"{n / 1_000_000:.1f}M"


def _ratio_color(ratio: float) -> str:
    """Return ANSI color code based on compression ratio.

    Args:
        ratio: Percentage of output characters saved.

    Returns:
        An ANSI escape sequence for the savings band.
    """
    if ratio >= 60:
        return GREEN
    if ratio >= 30:
        return YELLOW
    return RED


def _progress_bar(ratio: float, width: int = 20) -> str:
    """Render a progress bar with filled/empty blocks.

    Args:
        ratio: Percentage of output characters saved.
        width: Number of character cells available for the bar.

    Returns:
        A colored bar with filled and empty cells.
    """
    filled = round(ratio / 100 * width)
    empty = width - filled
    return f"{CYAN}{'█' * filled}{'░' * empty}{RESET}"


def _impact_bar(value: float, max_value: float, width: int = 10) -> str:
    """Render an impact bar proportional to max value.

    Args:
        value: Saved character count represented by this bar.
        max_value: Largest saved character count used to scale the bars.
        width: Number of character cells available for the bar.

    Returns:
        A colored bar, or an empty string when the maximum is not positive.
    """
    if max_value <= 0:
        return ""
    filled = max(1, round(value / max_value * width))
    return f"{CYAN}{'█' * filled}{RESET}"


def _print_header():
    """Print the heading for the lifetime savings report."""
    print()
    print(f"  {BOLD_GREEN}Token-Saver Savings (Lifetime){RESET}")
    print(f"  {BOLD_YELLOW}{'═' * WIDTH}{RESET}")


def _print_summary(lifetime):
    """Print lifetime character totals as estimated token savings.

    Args:
        lifetime: Lifetime aggregate counts returned by the savings tracker.
    """
    orig_tokens = _chars_to_tokens(lifetime["original"])
    comp_tokens = _chars_to_tokens(lifetime["compressed"])
    saved_tokens = _chars_to_tokens(lifetime["saved"])
    ratio = lifetime["ratio"]
    color = _ratio_color(ratio)

    print()
    print(
        f"  {'Total commands:':<20s} {BOLD_WHITE}{lifetime['commands']}{RESET}"
    )
    print(
        f"  {'Input tokens:':<20s} "
        f"{BOLD_WHITE}{_format_tokens(orig_tokens)}{RESET}"
    )
    print(
        f"  {'Output tokens:':<20s} "
        f"{BOLD_WHITE}{_format_tokens(comp_tokens)}{RESET}"
    )
    print(
        f"  {'Tokens saved:':<20s} "
        f"{BOLD_WHITE}{_format_tokens(saved_tokens)}{RESET}"
        f" {color}({ratio}%){RESET}"
    )
    print(
        f"  {'Efficiency:':<20s} {_progress_bar(ratio)}  {color}{ratio}%{RESET}"
    )


def _print_by_command(top_commands):
    """Print command-level savings and relative impact bars.

    Args:
        top_commands: Command aggregates ordered by descending saved characters.
    """
    if not top_commands:
        return

    print()
    print(f"  {BOLD_GREEN}By Command{RESET}")
    print(f"  {BOLD_YELLOW}{'─' * WIDTH}{RESET}")
    print()

    # Header row
    print(
        f"  {DIM}{'#':>3s}{RESET}  "
        f"{'Command':<20s}  "
        f"{'Count':>5s}  "
        f"{'Saved':>6s}  "
        f"{'Avg%':>5s}  "
        f"Impact"
    )

    max_saved = top_commands[0]["total_saved"] if top_commands else 1
    cmd_width = 20

    for i, cmd in enumerate(top_commands, 1):
        saved_tokens = _chars_to_tokens(cmd["total_saved"])
        ratio = cmd["avg_ratio"]
        color = _ratio_color(ratio)
        bar = _impact_bar(cmd["total_saved"], max_saved)
        name = cmd["command"][:cmd_width].ljust(cmd_width)

        print(
            f"  {DIM}{i:>3d}.{RESET} "
            f"{CYAN}{name}{RESET} "
            f"{cmd['count']:>5d}  "
            f"{BOLD_WHITE}{_format_tokens(saved_tokens):>6s}{RESET}  "
            f"{color}{ratio:>5.1f}%{RESET}  "
            f"{bar}"
        )

    print()


def _print_mismatches(mismatches):
    """Print processor mismatch counts when any were recorded.

    Args:
        mismatches: Processor mismatch aggregates ordered by event count.
    """
    if not mismatches:
        return

    print()
    print(f"  {BOLD_GREEN}Processor Mismatches{RESET}")
    print(f"  {BOLD_YELLOW}{'─' * WIDTH}{RESET}")
    print(
        f"  {DIM}Specialized processor ran but didn't compress enough.{RESET}"
    )
    print()
    for m in mismatches:
        print(f"  {CYAN}{m['processor']:<20s}{RESET} {m['count']:>5d} events")
    print()


def main(argv: list[str] | None = None) -> None:
    """Render tracker statistics as terminal text or JSON.

    Args:
        argv: Explicit arguments without the program name, or None to read
            sys.argv. Neither the supplied list nor sys.argv is modified.
    """
    console.use_utf8_io()
    arguments = sys.argv[1:] if argv is None else argv
    as_json = "--json" in arguments

    # Allow passing a session ID to show stats for a specific session
    session_id = None
    for i, arg in enumerate(arguments):
        if arg == "--session" and i < len(arguments) - 1:
            session_id = arguments[i + 1]

    tracker = tracker_lib.SavingsTracker(session_id=session_id)
    try:
        session = tracker.get_session_stats()
        lifetime = tracker.get_lifetime_stats()
        top_processors = tracker.get_top_processors(limit=5)
        top_commands = tracker.get_top_commands(limit=10)
        mismatches = tracker.get_processor_mismatches(limit=10)
    finally:
        tracker.close()

    if as_json:
        json.dump(
            {
                "session": session,
                "lifetime": lifetime,
                "top_processors": top_processors,
                "top_commands": top_commands,
                "mismatches": mismatches,
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return

    # --- Human-readable output ---
    if lifetime["commands"] == 0:
        print()
        print(f"  {BOLD_GREEN}Token-Saver Savings{RESET}")
        print(f"  {BOLD_YELLOW}{'═' * WIDTH}{RESET}")
        print()
        print("  No compressions recorded yet.")
        print()
        return

    _print_header()
    _print_summary(lifetime)
    _print_by_command(top_commands)
    _print_mismatches(mismatches)


if __name__ == "__main__":
    main()
