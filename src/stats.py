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


def _chars_to_tokens(n: int) -> int:
    """Estimate token count from character count."""
    from src import config  # noqa: PLC0415

    return max(1, round(n / config.get("chars_per_token"))) if n > 0 else 0


def _format_tokens(n: int) -> str:
    """Human-readable token count."""
    if n < 1_000:
        return f"{n} tokens"
    if n < 1_000_000:
        return f"{n / 1_000:.1f}k tokens"
    return f"{n / 1_000_000:.1f}M tokens"


def main():
    as_json = "--json" in sys.argv

    # Allow override for testing
    db_dir = os.environ.get("TOKEN_SAVER_DB_DIR")
    if db_dir:
        SavingsTracker.DB_DIR = db_dir
        SavingsTracker.DB_PATH = os.path.join(db_dir, "savings.db")

    tracker = SavingsTracker()
    session = tracker.get_session_stats()
    lifetime = tracker.get_lifetime_stats()
    top = tracker.get_top_processors(limit=5)
    tracker.close()

    if as_json:
        json.dump({"session": session, "lifetime": lifetime, "top_processors": top}, sys.stdout)
        sys.stdout.write("\n")
        return

    # --- Human-readable output ---
    print("Token-Saver Statistics")
    print("=" * 40)

    print("\nSession")
    print("-" * 40)
    if session["commands"] == 0:
        print("  No compressions in this session.")
    else:
        print(f"  Commands compressed:  {session['commands']}")
        print(f"  Original tokens:      {_format_tokens(_chars_to_tokens(session['original']))}")
        print(f"  Compressed tokens:    {_format_tokens(_chars_to_tokens(session['compressed']))}")
        saved = _format_tokens(_chars_to_tokens(session["saved"]))
        print(f"  Saved:                {saved} ({session['ratio']}%)")

    print("\nLifetime")
    print("-" * 40)
    if lifetime["commands"] == 0:
        print("  No compressions recorded yet.")
    else:
        print(f"  Sessions:             {lifetime['sessions']}")
        print(f"  Commands compressed:  {lifetime['commands']}")
        print(f"  Original tokens:      {_format_tokens(_chars_to_tokens(lifetime['original']))}")
        print(f"  Compressed tokens:    {_format_tokens(_chars_to_tokens(lifetime['compressed']))}")
        saved = _format_tokens(_chars_to_tokens(lifetime["saved"]))
        print(f"  Saved:                {saved} ({lifetime['ratio']}%)")

    if top:
        print("\nTop Processors")
        print("-" * 40)
        for entry in top:
            saved = _format_tokens(_chars_to_tokens(entry["saved"]))
            print(f"  {entry['processor']:<20s} {entry['count']:>4d} cmds, {saved} saved")


if __name__ == "__main__":
    main()
