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

"""Tests for version check module: comparison, fail-open."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.version_check
import src.version_check as version_check


class TestParseVersion:
    def test_simple(self):
        assert src.version_check._parse_version("1.0.0") == (1, 0, 0)

    def test_with_v_prefix(self):
        assert src.version_check._parse_version("v2.3.4") == (2, 3, 4)

    def test_with_whitespace(self):
        assert src.version_check._parse_version("  1.2.3  ") == (1, 2, 3)

    def test_comparison(self):
        assert src.version_check._parse_version(
            "1.2.0"
        ) > src.version_check._parse_version("1.1.9")
        assert src.version_check._parse_version(
            "2.0.0"
        ) > src.version_check._parse_version("1.99.99")
        assert src.version_check._parse_version(
            "1.0.0"
        ) == src.version_check._parse_version("v1.0.0")

    def test_prerelease_suffix_stripped(self):
        assert src.version_check._parse_version("1.0.0-beta") == (1, 0, 0)
        assert src.version_check._parse_version("2.1.0-rc.1") == (2, 1, 0)
        assert src.version_check._parse_version("v1.2.3-alpha") == (1, 2, 3)


class TestCheckForUpdate:
    def test_update_available(self):
        result = src.version_check.check_for_update(fetch_fn=lambda: "99.0.0")
        assert result is not None
        assert "99.0.0" in result
        assert "token-saver update" in result

    def test_already_up_to_date(self):
        import src

        result = src.version_check.check_for_update(
            fetch_fn=lambda: src.__version__
        )
        assert result is None

    def test_older_remote_version(self):
        result = src.version_check.check_for_update(fetch_fn=lambda: "0.0.1")
        assert result is None

    def test_fail_open_on_fetch_error(self):
        def failing_fetch():
            raise ConnectionError("Network down")

        result = src.version_check.check_for_update(fetch_fn=failing_fetch)
        assert result is None

    def test_fail_open_on_bad_version(self):
        def bad_version_fetch():
            return "not-a-version"

        result = src.version_check.check_for_update(fetch_fn=bad_version_fetch)
        assert result is None

    def test_fail_open_on_empty_version(self):
        result = src.version_check.check_for_update(fetch_fn=lambda: "")
        assert result is None

    def test_fail_open_on_none_version(self):
        def none_fetch():
            return None

        result = src.version_check.check_for_update(fetch_fn=none_fetch)
        assert result is None


class TestVersionCache:
    def test_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "cache.json")
        )
        src.version_check._write_cache("9.9.9")
        assert src.version_check._read_cache(ttl=3600) == "9.9.9"

    def test_read_expired_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "cache.json")
        )
        src.version_check._write_cache("9.9.9")
        # ttl=0 means anything written in the past is already stale
        assert src.version_check._read_cache(ttl=0) is None

    def test_read_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "nope.json")
        )
        assert src.version_check._read_cache(ttl=3600) is None

    def test_fresh_cache_skips_network(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "cache.json")
        )
        src.version_check._write_cache("99.0.0")

        def fail_fetch(*_a, **_k):
            raise AssertionError(
                "network should not be hit when cache is fresh"
            )

        monkeypatch.setattr(version_check, "_fetch_latest_version", fail_fetch)
        result = src.version_check.check_for_update()
        assert result is not None
        assert "99.0.0" in result

    def test_miss_fetches_and_populates_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "cache.json")
        )
        calls = []

        def counting_fetch(*_a, **_k):
            calls.append(1)
            return "99.0.0"

        monkeypatch.setattr(
            version_check, "_fetch_latest_version", counting_fetch
        )
        src.version_check.check_for_update()
        # The second call should read the cache without fetching again.
        src.version_check.check_for_update()
        assert len(calls) == 1
        assert src.version_check._read_cache(ttl=3600) == "99.0.0"

    def test_fetch_fn_override_bypasses_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_check, "_cache_path", lambda: str(tmp_path / "cache.json")
        )
        src.version_check._write_cache("0.0.1")  # stale-but-present cache
        # fetch_fn path must ignore the cache entirely
        result = src.version_check.check_for_update(fetch_fn=lambda: "99.0.0")
        assert result is not None
        assert "99.0.0" in result
