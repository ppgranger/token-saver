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

"""Exercise resource cleanup at the best-effort session hook boundary."""

import io
import sqlite3
import sys
from unittest import mock

import pytest

from src import hook_session
from src import tracker as tracker_lib


def test_render_failure_closes_database_and_keeps_hook_successful(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(tracker_lib.SavingsTracker, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(tracker_lib.SavingsTracker, "DB_PATH", None)
    tracker = tracker_lib.SavingsTracker(session_id="failed-render")
    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"session_id":"failed-render"}')
    )
    try:
        with (
            mock.patch.object(
                hook_session.tracker_lib,
                "SavingsTracker",
                return_value=tracker,
            ),
            mock.patch.object(
                tracker,
                "format_stats_message",
                side_effect=sqlite3.OperationalError("fixture render failure"),
            ),
            pytest.raises(SystemExit) as exited,
        ):
            hook_session.main()
        assert exited.value.code == 0
        assert capsys.readouterr().out == ""
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            tracker.conn.execute("SELECT 1")
    finally:
        tracker.close()
