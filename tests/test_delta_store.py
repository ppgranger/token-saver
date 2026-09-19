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

"""Storage boundaries for redacted, opt-in Delta history."""

import concurrent.futures
import json
import os
import re
import sqlite3
import stat

import pytest

import src
from src import delta_store


def test_roundtrip_reopen_and_scope_isolation(tmp_path):
    directory = str(tmp_path / "delta")
    payload = {"family": "pytest", "summary": "2 échecs", "diagnostics": []}
    with delta_store.Store(directory) as store:
        first = store.save("project-one:pytest", payload)
        second = store.save("project-two:pytest", {"summary": "success"})
        assert re.fullmatch(r"[0-9a-f]{32}", first)
        assert first != second
        assert store.latest("project-one:pytest") == (first, payload)
        assert store.latest("unknown") is None
        assert store.get("0" * 32) is None
    with delta_store.Store(directory) as store:
        assert store.get(first) == payload
        assert store.get(second) == {"summary": "success"}
    raw_database = (tmp_path / "delta" / "snapshots.sqlite3").read_bytes()
    assert b"project-one:pytest" not in raw_database
    assert b"project-two:pytest" not in raw_database


def test_reads_expire_records_at_the_retention_boundary(tmp_path, monkeypatch):
    clock = [10000.0]
    monkeypatch.setattr(delta_store.time, "time", lambda: clock[0])
    with delta_store.Store(str(tmp_path), retention_hours=1) as store:
        expired = store.save("scope", {"summary": "old"})
        clock[0] += 3599
        assert store.get(expired) is not None
        latest = store.save("scope", {"summary": "new"})
        clock[0] += 1
        assert store.get(expired) is None
        assert store.latest("scope") == (latest, {"summary": "new"})
        clock[0] += 3600
        assert store.latest("scope") is None
        assert store.clear() == 0


def test_global_quota_keeps_newest_across_scopes(tmp_path, monkeypatch):
    monkeypatch.setattr(delta_store.time, "time", lambda: 10000)
    with delta_store.Store(str(tmp_path), max_runs=2) as store:
        first = store.save("one", {"summary": "first"})
        second = store.save("two", {"summary": "second"})
        third = store.save("one", {"summary": "third"})
        assert store.get(first) is None
        assert store.get(second) == {"summary": "second"}
        assert store.latest("one") == (third, {"summary": "third"})
        assert store.clear() == 2
        assert store.clear() == 0
        assert store.get(third) is None


def test_reopen_with_smaller_quota_prunes_existing_records(tmp_path):
    with delta_store.Store(str(tmp_path), max_runs=3) as store:
        store.save("scope", {"n": 1})
        store.save("scope", {"n": 2})
        latest = store.save("scope", {"n": 3})
    with delta_store.Store(str(tmp_path), max_runs=1) as store:
        assert store.latest("scope") == (latest, {"n": 3})
        assert store.clear() == 1


def test_clock_rollback_keeps_current_run_and_expires_future_records(
    tmp_path, monkeypatch
):
    clock = [10000.0]
    monkeypatch.setattr(delta_store.time, "time", lambda: clock[0])
    with delta_store.Store(str(tmp_path), max_runs=1) as store:
        previous = store.save("scope", {"summary": "before clock change"})
        clock[0] -= 60
        current = store.save("scope", {"summary": "after clock change"})
        assert store.get(current) == {"summary": "after clock change"}
        assert store.latest("scope") == (
            current,
            {"summary": "after clock change"},
        )
        assert store.get(previous) is None


def test_clock_rollback_expires_future_records_on_read(tmp_path, monkeypatch):
    clock = [10000.0]
    monkeypatch.setattr(delta_store.time, "time", lambda: clock[0])
    with delta_store.Store(str(tmp_path)) as store:
        run_id = store.save("scope", {"summary": "before clock change"})
        clock[0] -= 1
        assert store.get(run_id) is None
        assert store.latest("scope") is None


@pytest.mark.parametrize(
    "run_id", ["../snapshot", "a" * 33, "A" * 32, "", None]
)
def test_rejects_invalid_run_identifiers(tmp_path, run_id):
    with (
        delta_store.Store(str(tmp_path)) as store,
        pytest.raises(ValueError, match="Invalid Delta run identifier"),
    ):
        store.get(run_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retention_hours", 0),
        ("retention_hours", 169),
        ("retention_hours", True),
        ("max_runs", 0),
        ("max_runs", 1001),
        ("max_runs", 1.5),
    ],
)
def test_rejects_invalid_bounds_before_creating_storage(tmp_path, field, value):
    directory = tmp_path / "delta"
    with pytest.raises(ValueError, match="storage bound"):
        delta_store.Store(str(directory), **{field: value})
    assert not directory.exists()


def test_payload_limit_uses_utf8_bytes_and_preserves_existing_data(tmp_path):
    with delta_store.Store(str(tmp_path)) as store:
        run_id = store.save("scope", {"summary": "kept"})
        oversized = "é" * (delta_store.MAX_PAYLOAD_BYTES // 2)
        with pytest.raises(ValueError, match="storage limit"):
            store.save("scope", {"summary": oversized})
        with pytest.raises(ValueError, match="JSON object"):
            store.save("scope", [])
        with pytest.raises(ValueError, match="JSON compliant"):
            store.save("scope", {"invalid": float("nan")})
        assert store.latest("scope") == (run_id, {"summary": "kept"})


def test_corrupt_database_is_not_recreated(tmp_path):
    database = tmp_path / "snapshots.sqlite3"
    original = b"corrupt snapshot database: keep this for inspection"
    database.write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        delta_store.Store(str(tmp_path))
    assert database.read_bytes() == original


def test_unrecognized_schema_is_not_replaced(tmp_path):
    database = tmp_path / "snapshots.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('preserve')")
    with pytest.raises(ValueError, match="Unrecognized"):
        delta_store.Store(str(tmp_path))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone() == (
            "preserve",
        )


@pytest.mark.parametrize(
    "corrupt_payload", ["not json", json.dumps(["wrong"]), b"wrong type"]
)
def test_invalid_payload_is_reported_without_deleting_record(
    tmp_path, corrupt_payload
):
    with delta_store.Store(str(tmp_path)) as store:
        run_id = store.save("scope", {"summary": "valid"})
        with sqlite3.connect(tmp_path / "snapshots.sqlite3") as connection:
            connection.execute(
                "UPDATE snapshots SET payload = ?", (corrupt_payload,)
            )
        with pytest.raises(ValueError, match=r"Expecting value|Invalid Delta"):
            store.get(run_id)
        assert store.clear() == 1


def test_default_directory_respects_override_and_platform_path(
    tmp_path, monkeypatch
):
    override = tmp_path / "override"
    platform_data = tmp_path / "platform"
    monkeypatch.setenv("TOKEN_SAVER_DB_DIR", str(override))
    monkeypatch.setattr(src, "data_dir", lambda: str(platform_data))
    with delta_store.Store() as store:
        store.save("scope", {})
    assert (override / "delta" / "snapshots.sqlite3").is_file()
    assert not platform_data.exists()
    monkeypatch.delenv("TOKEN_SAVER_DB_DIR")
    with delta_store.Store() as store:
        store.save("scope", {})
    assert (platform_data / "delta" / "snapshots.sqlite3").is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_directory_and_database_are_private(tmp_path):
    directory = tmp_path / "delta"
    directory.mkdir(mode=0o755)
    with delta_store.Store(str(directory)) as store:
        store.save("scope", {"summary": "private"})
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert (
        stat.S_IMODE((directory / "snapshots.sqlite3").stat().st_mode) == 0o600
    )


@pytest.mark.skipif(os.name == "nt", reason="Windows symlinks need privileges")
@pytest.mark.parametrize("target", ["directory", "database", "journal"])
def test_rejects_symlink_data_paths(tmp_path, target):
    directory = tmp_path / "delta"
    outside = tmp_path / "outside"
    outside.mkdir()
    if target == "directory":
        directory.symlink_to(outside, target_is_directory=True)
    else:
        directory.mkdir()
        filename = "snapshots.sqlite3"
        if target == "journal":
            filename += "-journal"
        (outside / filename).write_bytes(b"untouched")
        (directory / filename).symlink_to(outside / filename)
    with pytest.raises(ValueError, match="Unsafe Delta"):
        delta_store.Store(str(directory))
    if target != "directory":
        assert (outside / filename).read_bytes() == b"untouched"


def test_rejects_nonregular_database(tmp_path):
    (tmp_path / "snapshots.sqlite3").mkdir()
    with pytest.raises(ValueError, match="Unsafe Delta data file"):
        delta_store.Store(str(tmp_path))


@pytest.mark.parametrize("existing", ["directory", "file", "missing"])
def test_exclusive_create_distinguishes_windows_directory_access_error(
    tmp_path, monkeypatch, existing
):
    database = tmp_path / "snapshots.sqlite3"
    if existing == "directory":
        database.mkdir()
    elif existing == "file":
        database.write_bytes(b"untouched")
    original_open = delta_store.os.open
    denied = PermissionError("synthetic access denial")

    def deny_database_create(path, *args, **kwargs):
        if str(path) == str(database):
            raise denied
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(delta_store.os, "open", deny_database_create)
    if existing == "directory":
        with pytest.raises(ValueError, match="Unsafe Delta data file"):
            delta_store.Store(str(tmp_path))
        assert database.is_dir()
    else:
        with pytest.raises(PermissionError) as failure:
            delta_store.Store(str(tmp_path))
        assert failure.value is denied
        if existing == "file":
            assert database.read_bytes() == b"untouched"
        else:
            assert not database.exists()


def test_rejects_hardlinked_database_without_changing_target(tmp_path):
    directory = tmp_path / "delta"
    directory.mkdir()
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"untouched")
    os.link(outside, directory / "snapshots.sqlite3")
    with pytest.raises(ValueError, match="Unsafe Delta data file"):
        delta_store.Store(str(directory))
    assert outside.read_bytes() == b"untouched"


def test_open_tolerates_sqlite_removing_optional_sidecars(
    tmp_path, monkeypatch
):
    directory = tmp_path / "delta"
    with delta_store.Store(str(directory)) as store:
        run_id = store.save("scope", {"summary": "kept"})
    journal = directory / "snapshots.sqlite3-journal"
    journal.write_bytes(b"")
    original = delta_store.os.chmod

    def remove_before_inspection(path, *args, **kwargs):
        if str(path) == str(journal) and journal.exists():
            # A second SQLite connection can unlink its completed journal
            # between the first store's path check and metadata operation.
            journal.unlink()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(delta_store.os, "chmod", remove_before_inspection)
    with delta_store.Store(str(directory)) as store:
        assert store.get(run_id) == {"summary": "kept"}


def test_independent_concurrent_stores_commit_distinct_records(tmp_path):
    directory = str(tmp_path / "delta")

    def save_one(number):
        with delta_store.Store(directory, max_runs=5) as store:
            return store.save("scope", {"number": number})

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        identifiers = list(executor.map(save_one, range(12)))
    assert len(set(identifiers)) == 12
    with delta_store.Store(directory, max_runs=5) as store:
        assert sum(store.get(run_id) is not None for run_id in identifiers) == 5


def test_context_manager_closes_after_caller_error(tmp_path):
    with (
        pytest.raises(RuntimeError, match="caller failure"),
        delta_store.Store(str(tmp_path)) as store,
    ):
        raise RuntimeError("caller failure")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        store.get("0" * 32)
    store.close()
