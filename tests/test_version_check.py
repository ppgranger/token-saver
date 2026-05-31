"""Tests for version check module: comparison, fail-open."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.version_check as version_check
from src.version_check import (
    _parse_version,
    _read_cache,
    _write_cache,
    check_for_update,
)


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("1.0.0") == (1, 0, 0)

    def test_with_v_prefix(self):
        assert _parse_version("v2.3.4") == (2, 3, 4)

    def test_with_whitespace(self):
        assert _parse_version("  1.2.3  ") == (1, 2, 3)

    def test_comparison(self):
        assert _parse_version("1.2.0") > _parse_version("1.1.9")
        assert _parse_version("2.0.0") > _parse_version("1.99.99")
        assert _parse_version("1.0.0") == _parse_version("v1.0.0")

    def test_prerelease_suffix_stripped(self):
        assert _parse_version("1.0.0-beta") == (1, 0, 0)
        assert _parse_version("2.1.0-rc.1") == (2, 1, 0)
        assert _parse_version("v1.2.3-alpha") == (1, 2, 3)


class TestCheckForUpdate:
    def test_update_available(self):
        result = check_for_update(fetch_fn=lambda: "99.0.0")
        assert result is not None
        assert "99.0.0" in result
        assert "token-saver update" in result

    def test_already_up_to_date(self):
        from src import __version__

        result = check_for_update(fetch_fn=lambda: __version__)
        assert result is None

    def test_older_remote_version(self):
        result = check_for_update(fetch_fn=lambda: "0.0.1")
        assert result is None

    def test_fail_open_on_fetch_error(self):
        def failing_fetch():
            raise ConnectionError("Network down")

        result = check_for_update(fetch_fn=failing_fetch)
        assert result is None

    def test_fail_open_on_bad_version(self):
        def bad_version_fetch():
            return "not-a-version"

        result = check_for_update(fetch_fn=bad_version_fetch)
        assert result is None

    def test_fail_open_on_empty_version(self):
        result = check_for_update(fetch_fn=lambda: "")
        assert result is None

    def test_fail_open_on_none_version(self):
        def none_fetch():
            return None

        result = check_for_update(fetch_fn=none_fetch)
        assert result is None


class TestVersionCache:
    def test_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "cache.json"))
        _write_cache("9.9.9")
        assert _read_cache(ttl=3600) == "9.9.9"

    def test_read_expired_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "cache.json"))
        _write_cache("9.9.9")
        # ttl=0 means anything written in the past is already stale
        assert _read_cache(ttl=0) is None

    def test_read_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "nope.json"))
        assert _read_cache(ttl=3600) is None

    def test_fresh_cache_skips_network(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "cache.json"))
        _write_cache("99.0.0")

        def fail_fetch(*_a, **_k):
            raise AssertionError("network should not be hit when cache is fresh")

        monkeypatch.setattr(version_check, "_fetch_latest_version", fail_fetch)
        result = check_for_update()
        assert result is not None
        assert "99.0.0" in result

    def test_miss_fetches_and_populates_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "cache.json"))
        calls = []

        def counting_fetch(*_a, **_k):
            calls.append(1)
            return "99.0.0"

        monkeypatch.setattr(version_check, "_fetch_latest_version", counting_fetch)
        check_for_update()
        check_for_update()  # second call should read the cache, not refetch
        assert len(calls) == 1
        assert _read_cache(ttl=3600) == "99.0.0"

    def test_fetch_fn_override_bypasses_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(version_check, "_cache_path", lambda: str(tmp_path / "cache.json"))
        _write_cache("0.0.1")  # stale-but-present cache
        # fetch_fn path must ignore the cache entirely
        result = check_for_update(fetch_fn=lambda: "99.0.0")
        assert result is not None
        assert "99.0.0" in result
