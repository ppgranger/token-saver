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

"""SessionStart hook: display token-saver stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Installed entrypoints must establish the package root first.
# pylint: disable=wrong-import-position
import src
from src import console
from src import tracker as tracker_lib

# pylint: enable=wrong-import-position


def _check_migration_message():
    """Return a one-time migration notice if upgrading to v2.0.

    Returns:
        A migration notice, or None if its sentinel already exists.
    """
    sentinel = os.path.join(src.data_dir(), ".migrated_v2")
    if os.path.exists(sentinel):
        return None

    os.makedirs(src.data_dir(), exist_ok=True)
    try:
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write(src.__version__)
    except OSError:
        pass

    return (
        f"token-saver v{src.__version__} — Now a native Claude Code plugin! "
        "Manage via /plugin or keep using manual install."
    )


def main():
    """Emit a best-effort session-start statistics message as JSON."""
    console.use_utf8_io()
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
        tracker = tracker_lib.SavingsTracker(session_id=cc_session)
        try:
            message = tracker.format_stats_message()
        finally:
            tracker.close()
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:  # noqa: S110
        pass

    if message is None:
        sys.exit(0)

    # Best-effort update notification — uses a 1s HTTP timeout so the
    # total hook time stays well under Claude's 3s hook timeout.
    try:
        # Defer this adapter dependency until its command or hook is used.
        # pylint: disable-next=import-outside-toplevel
        from src import version_check  # noqa: PLC0415

        update_msg = version_check.check_for_update()
        if update_msg:
            message = f"{message} | {update_msg}"
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:  # noqa: S110
        pass

    # One-time migration notice for v2.0
    try:
        migration_msg = _check_migration_message()
        if migration_msg:
            message = f"{message} | {migration_msg}"
    # This best-effort boundary must not block the host command or hook.
    # pylint: disable-next=broad-exception-caught
    except Exception:  # noqa: S110
        pass

    json.dump({"systemMessage": message}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
