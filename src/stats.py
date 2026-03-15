#!/usr/bin/env python3
"""Display token-saver savings statistics.

Usage:
    python3 stats.py              # Human-readable summary
    python3 stats.py --json       # JSON output for scripting
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker import SavingsTracker

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
    """Estimate token count from character count."""
    from src import config  # noqa: PLC0415

    return max(1, round(n / config.get("chars_per_token"))) if n > 0 else 0


def _format_tokens(n: int) -> str:
    """Human-readable token count."""
    if n < 1_000:
        return f"{n}"
    if n < 1_000_000:
        return f"{n / 1_000:.1f}K"
    return f"{n / 1_000_000:.1f}M"


def _ratio_color(ratio: float) -> str:
    """Return ANSI color code based on compression ratio."""
    if ratio >= 60:
        return GREEN
    if ratio >= 30:
        return YELLOW
    return RED


def _progress_bar(ratio: float, width: int = 20) -> str:
    """Render a progress bar with filled/empty blocks."""
    filled = round(ratio / 100 * width)
    empty = width - filled
    return f"{CYAN}{'█' * filled}{'░' * empty}{RESET}"


def _impact_bar(value: float, max_value: float, width: int = 10) -> str:
    """Render an impact bar proportional to max value."""
    if max_value <= 0:
        return ""
    filled = max(1, round(value / max_value * width))
    return f"{CYAN}{'█' * filled}{RESET}"


def _print_header():
    print()
    print(f"  {BOLD_GREEN}Token-Saver Savings (Lifetime){RESET}")
    print(f"  {BOLD_YELLOW}{'═' * WIDTH}{RESET}")


def _print_summary(lifetime):
    orig_tokens = _chars_to_tokens(lifetime["original"])
    comp_tokens = _chars_to_tokens(lifetime["compressed"])
    saved_tokens = _chars_to_tokens(lifetime["saved"])
    ratio = lifetime["ratio"]
    color = _ratio_color(ratio)

    print()
    print(f"  {'Total commands:':<20s} {BOLD_WHITE}{lifetime['commands']}{RESET}")
    print(f"  {'Input tokens:':<20s} {BOLD_WHITE}{_format_tokens(orig_tokens)}{RESET}")
    print(f"  {'Output tokens:':<20s} {BOLD_WHITE}{_format_tokens(comp_tokens)}{RESET}")
    print(
        f"  {'Tokens saved:':<20s} {BOLD_WHITE}{_format_tokens(saved_tokens)}{RESET}"
        f" {color}({ratio}%){RESET}"
    )
    print(f"  {'Efficiency:':<20s} {_progress_bar(ratio)}  {color}{ratio}%{RESET}")


def _print_by_command(top_commands):
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


def main():
    as_json = "--json" in sys.argv

    # Allow override for testing
    db_dir = os.environ.get("TOKEN_SAVER_DB_DIR")
    if db_dir:
        SavingsTracker.DB_DIR = db_dir
        SavingsTracker.DB_PATH = os.path.join(db_dir, "savings.db")

    # Allow passing a session ID to show stats for a specific session
    session_id = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--session" and i < len(sys.argv) - 1:
            session_id = sys.argv[i + 1]

    tracker = SavingsTracker(session_id=session_id)
    session = tracker.get_session_stats()
    lifetime = tracker.get_lifetime_stats()
    top_processors = tracker.get_top_processors(limit=5)
    top_commands = tracker.get_top_commands(limit=10)
    tracker.close()

    if as_json:
        json.dump(
            {
                "session": session,
                "lifetime": lifetime,
                "top_processors": top_processors,
                "top_commands": top_commands,
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


if __name__ == "__main__":
    main()
