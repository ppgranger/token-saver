#!/usr/bin/env python3
"""SessionStart hook: display token-saver stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker import SavingsTracker


def main():
    try:
        tracker = SavingsTracker()
        message = tracker.format_stats_message()
        tracker.close()

        # Append update notification if available
        try:
            from src.version_check import check_for_update  # noqa: PLC0415

            update_msg = check_for_update()
            if update_msg:
                message = f"{message} | {update_msg}"
        except Exception:  # noqa: S110
            pass

        result = {"systemMessage": message}
        json.dump(result, sys.stdout)
    except Exception:  # noqa: S110
        # Never break session start
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
