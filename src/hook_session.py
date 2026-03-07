#!/usr/bin/env python3
"""SessionStart hook: display token-saver stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker import SavingsTracker


def _check_migration_message():
    """Return a one-time migration notice if upgrading to v2.0."""
    from src import __version__, data_dir  # noqa: PLC0415

    sentinel = os.path.join(data_dir(), ".migrated_v2")
    if os.path.exists(sentinel):
        return None

    os.makedirs(data_dir(), exist_ok=True)
    try:
        with open(sentinel, "w") as f:
            f.write(__version__)
    except OSError:
        pass

    return (
        f"token-saver v{__version__} — Now a native Claude Code plugin! "
        "Manage via /plugin or keep using manual install."
    )


def main():
    message = None

    # Read Claude Code's session_id from stdin JSON payload
    cc_session = None
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            cc_session = data.get("session_id")
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        tracker = SavingsTracker(session_id=cc_session)
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

    # One-time migration notice for v2.0
    try:
        migration_msg = _check_migration_message()
        if migration_msg:
            message = f"{message} | {migration_msg}"
    except Exception:  # noqa: S110
        pass

    json.dump({"systemMessage": message}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
