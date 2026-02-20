#!/usr/bin/env python3
"""SessionStart hook: display token-saver stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker import SavingsTracker


def main():
    message = None

    try:
        tracker = SavingsTracker()
        message = tracker.format_stats_message()
        tracker.close()
    except Exception:  # noqa: S110
        pass

    if message is None:
        sys.exit(0)

    # Best-effort update notification — uses a 1s HTTP timeout so the
    # total hook time stays well under Claude's 3s hook timeout.
    try:
        from src.version_check import check_for_update  # noqa: PLC0415

        update_msg = check_for_update()
        if update_msg:
            message = f"{message} | {update_msg}"
    except Exception:  # noqa: S110
        pass

    json.dump({"systemMessage": message}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
