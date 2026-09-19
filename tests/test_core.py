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

"""Test shared compression and the Antigravity hook."""

import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.tracker
from src import core

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestShouldCompress:
    def test_compressible_command(self):
        assert core.should_compress("git status") is True

    def test_excluded_command(self):
        assert core.should_compress("sudo git status") is False

    def test_non_matching_command(self):
        assert core.should_compress("echo hello") is False


class TestCompress:
    def test_failed_extension_logs_no_command_output_or_exception(self, caplog):
        compressor = mock.Mock()
        compressor.compress.side_effect = RuntimeError("private-exception")
        compressor.last_event = {}
        result = core.compress(
            "pytest private-argument",
            "AssertionError: private-output",
            engine=compressor,
            exit_code=1,
        )
        assert result.compressed == "AssertionError: private-output"
        assert "Compression failed" in caplog.text
        for value in (
            "private-argument",
            "private-output",
            "private-exception",
        ):
            assert value not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)

    def test_compresses_verbose_output(self):
        output = "\n".join(f"{i:07x} commit {i}" for i in range(60)) + "\n"
        result = core.compress("git log --oneline", output)
        assert result.was_compressed is True
        assert result.processor == "git"
        assert result.compressed_len < result.original_len

    def test_unmatched_command_routes_to_generic(self):
        # Generic (priority 999) handles everything; a tiny clean output that
        # generic leaves unchanged is reported as not-compressed.
        result = core.compress("nonsense-cmd", "tidy")
        assert result.was_compressed is False
        assert result.original_len == len("tidy")

    def test_result_carries_original_len(self):
        result = core.compress("git status", "x" * 100)
        assert result.original_len == 100


class TestRecording:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_dir = src.tracker.SavingsTracker.DB_DIR
        self._orig_path = src.tracker.SavingsTracker.DB_PATH
        src.tracker.SavingsTracker.DB_DIR = self.tmp_dir
        src.tracker.SavingsTracker.DB_PATH = os.path.join(
            self.tmp_dir, "savings.db"
        )

    def teardown_method(self):
        db = os.path.join(self.tmp_dir, "savings.db")
        for f in (db, db + "-wal", db + "-shm"):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self.tmp_dir)
        src.tracker.SavingsTracker.DB_DIR = self._orig_dir
        src.tracker.SavingsTracker.DB_PATH = self._orig_path

    def test_record_result_records_saving(self):
        result = core.CompressResult(
            compressed="x" * 20,
            processor="git",
            was_compressed=True,
            is_mismatch=False,
            attempted_processor="git",
            original_len=100,
            compressed_len=20,
        )
        core.record_result(result, "git status", "antigravity_cli")
        tracker = src.tracker.SavingsTracker(session_id="any")
        lifetime = tracker.get_lifetime_stats()
        assert lifetime["commands"] == 1
        assert lifetime["original"] == 100
        tracker.close()

    def test_record_result_records_mismatch(self):
        result = core.CompressResult(
            compressed="x" * 95,
            processor="generic",
            was_compressed=False,
            is_mismatch=True,
            attempted_processor="docker",
            original_len=100,
            compressed_len=95,
        )
        core.record_result(result, "docker ps", "antigravity_cli")
        tracker = src.tracker.SavingsTracker(session_id="any")
        rows = tracker.get_processor_mismatches()
        assert len(rows) == 1
        assert rows[0]["processor"] == "docker"
        tracker.close()


class TestAntigravityHook:
    def _run_hook(self, payload):
        return subprocess.run(  # noqa: PLW1510
            [sys.executable, "antigravity/hook_aftertool.py"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_DIR,
            timeout=20,
        )

    def test_compresses_git_output(self):
        out = "\n".join(f"{i:07x} commit {i}" for i in range(60)) + "\n"
        payload = {
            "tool_input": {"command": "git log --oneline -60"},
            "tool_response": {"output": out},
            "hook_event_name": "AfterTool",
        }
        r = self._run_hook(payload)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["decision"] == "deny"
        assert len(data["reason"]) < len(out)

    def test_gate_passes_through_non_compressible(self):
        payload = {
            "tool_input": {"command": "echo hello"},
            "tool_response": {"output": "hello\n" * 200},
            "hook_event_name": "AfterTool",
        }
        r = self._run_hook(payload)
        assert r.returncode == 0
        assert json.loads(r.stdout) == {}

    def test_empty_output_passthrough(self):
        payload = {
            "tool_input": {"command": "git status"},
            "tool_response": {"output": ""},
            "hook_event_name": "AfterTool",
        }
        r = self._run_hook(payload)
        assert r.returncode == 0
