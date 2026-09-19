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

"""Exercise optional persistence through its write-only integration contract."""

import logging
import os
import subprocess
import sys
from unittest import mock

import pytest

from src import core
from src import telemetry


class MemoryWriter:
    """Write-only tracker substitute with explicit failure and close state."""

    def __init__(self, *, fail=False):
        self.rows = []
        self.closed = False
        self.fail = fail

    def record_saving(self, **row):
        self._record(row)

    def record_mismatch(self, **row):
        self._record(row)

    def _record(self, row):
        if self.fail:
            raise RuntimeError("synthetic-private-error")
        self.rows.append(row)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("mismatch", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_injected_writer_closes_after_success_and_failure(
    mismatch, fail, caplog
):
    writer = MemoryWriter(fail=fail)
    factory = mock.Mock(return_value=writer)
    if mismatch:
        telemetry.record_mismatches(
            [("test-private-command", "test", 100)],
            "claude_code",
            tracker_factory=factory,
        )
    else:
        telemetry.record_saving(
            "test-private-command",
            "test",
            100,
            20,
            "claude_code",
            tracker_factory=factory,
        )
    factory.assert_called_once_with()
    assert writer.closed
    assert len(writer.rows) == (0 if fail else 1)
    if not fail:
        assert writer.rows[0]["original_size"] == 100
        assert writer.rows[0]["platform"] == "claude_code"
        if not mismatch:
            assert writer.rows[0]["compressed_size"] == 20
    else:
        assert "failed" in caplog.text
        assert "synthetic-private-error" not in caplog.text
        assert "test-private-command" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)


def test_empty_mismatches_do_not_open_persistence():
    factory = mock.Mock(side_effect=AssertionError("must stay lazy"))
    telemetry.record_mismatches([], "claude_code", tracker_factory=factory)
    factory.assert_not_called()


def test_writer_initialization_failure_stays_optional(caplog):
    factory = mock.Mock(side_effect=OSError("synthetic-private-path"))
    telemetry.record_saving(
        "test-private-command",
        "test",
        100,
        20,
        "claude_code",
        tracker_factory=factory,
    )
    assert "Tracking failed" in caplog.text
    assert "synthetic-private" not in caplog.text


def test_audit_initializes_on_use_and_writes_utf8(tmp_path, monkeypatch):
    logger = logging.Logger("token-saver-test-audit")
    monkeypatch.setattr(telemetry, "_AUDIT", logger)
    directory = tmp_path / "journal"
    monkeypatch.setattr(telemetry.src, "data_dir", lambda: str(directory))
    assert not directory.exists()
    try:
        core.audit_log("git log résumé", "git", 100, 20)
        text = (directory / "audit.log").read_text(encoding="utf-8")
        assert "résumé" in text
        assert "ratio=80.0%" in text
        assert len(logger.handlers) == 1
        core.audit_log("git status", "git", 0, 0)
        assert len(logger.handlers) == 1
    finally:
        for handler in logger.handlers:
            handler.close()


def test_audit_failure_is_optional_and_can_retry(tmp_path, monkeypatch, caplog):
    logger = logging.Logger("token-saver-test-audit-failure")
    monkeypatch.setattr(telemetry, "_AUDIT", logger)
    directory = tmp_path / "journal"
    directory.write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(telemetry.src, "data_dir", lambda: str(directory))
    core.audit_log("test-private-command", "test", 100, 20)
    assert "Audit logging failed" in caplog.text
    assert "test-private-command" not in caplog.text
    assert logger.handlers == []
    directory.unlink()
    try:
        core.audit_log("git status", "git", 100, 20)
        assert (directory / "audit.log").is_file()
    finally:
        for handler in logger.handlers:
            handler.close()


def test_audit_write_failure_never_dumps_record_or_traceback(
    tmp_path, monkeypatch, caplog, capsys
):
    logger = logging.Logger("token-saver-test-audit-write-failure")
    monkeypatch.setattr(telemetry, "_AUDIT", logger)
    monkeypatch.setattr(telemetry.src, "data_dir", lambda: str(tmp_path))
    core.audit_log("git status", "git", 100, 20)
    handler = logger.handlers[0]
    failing_stream = mock.Mock(wraps=handler.stream)
    failing_stream.write.side_effect = OSError("synthetic-private-error")
    try:
        with mock.patch.object(handler, "stream", failing_stream):
            core.audit_log("test-private-command", "test", 100, 20)
        assert "Audit logging failed" in caplog.text
        emitted = capsys.readouterr()
        for forbidden in ("test-private-command", "synthetic-private-error"):
            assert forbidden not in caplog.text
            assert forbidden not in emitted.err
        assert "Traceback" not in emitted.err
        assert all(record.exc_info is None for record in caplog.records)
    finally:
        handler.close()


def test_core_import_and_compression_do_not_initialize_persistence(tmp_path):
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("TOKEN_SAVER_"):
            environment.pop(key)
    environment.update(
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        APPDATA=str(tmp_path),
        TOKEN_SAVER_DB_DIR=str(tmp_path),
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from src import core
from src import engine
from src.processors import generic
compressor = engine.CompressionEngine(
    processors=[generic.GenericProcessor()], settings={"enabled": False}
)
result = core.compress("git status", "captured output", engine=compressor)
assert result.compressed == "captured output"
assert core.should_compress("git status")
assert "scripts.hook_pretool" not in sys.modules
""",
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_core_uses_falsey_injected_backend_without_discovery(monkeypatch):
    class Backend:
        last_event = {"attempted_processor": "external", "is_mismatch": True}

        def __bool__(self):
            return False

        def compress(self, command, output, *, exit_code=None):
            assert command == "fixture"
            assert output == "details"
            assert exit_code == 1
            return "external result", "external", True

    constructor = mock.Mock(side_effect=AssertionError("unexpected discovery"))
    monkeypatch.setattr(core.engine_lib, "CompressionEngine", constructor)
    result = core.compress("fixture", "details", engine=Backend(), exit_code=1)
    assert result.processor == "external"
    assert result.compressed == "external result"
    assert result.is_mismatch
    constructor.assert_not_called()
