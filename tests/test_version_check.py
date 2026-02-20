"""Tests for version check module: comparison, fail-open."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.version_check import (
    _parse_version,
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
