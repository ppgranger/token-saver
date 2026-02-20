"""Tests for the configuration system."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config


class TestConfig:
    def setup_method(self):
        config.reload()

    def test_default_values(self, monkeypatch):
        # Clear any TOKEN_SAVER_* env vars so defaults are not overridden
        for key in list(os.environ):
            if key.startswith("TOKEN_SAVER_"):
                monkeypatch.delenv(key)
        config.reload()
        assert config.get("min_input_length") == 200
        assert config.get("min_compression_ratio") == 0.10
        assert config.get("wrap_timeout") == 300
        assert config.get("debug") is False

    def test_unknown_key_returns_none(self):
        assert config.get("nonexistent_key") is None

    def test_env_override_int(self):
        os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"] = "500"  # noqa: S105
        config.reload()
        try:
            assert config.get("min_input_length") == 500
        finally:
            del os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"]
            config.reload()

    def test_env_override_float(self):
        os.environ["TOKEN_SAVER_MIN_COMPRESSION_RATIO"] = "0.25"  # noqa: S105
        config.reload()
        try:
            assert config.get("min_compression_ratio") == 0.25
        finally:
            del os.environ["TOKEN_SAVER_MIN_COMPRESSION_RATIO"]
            config.reload()

    def test_env_override_bool(self):
        os.environ["TOKEN_SAVER_DEBUG"] = "true"  # noqa: S105
        config.reload()
        try:
            assert config.get("debug") is True
        finally:
            del os.environ["TOKEN_SAVER_DEBUG"]
            config.reload()

    def test_invalid_env_value_ignored(self):
        os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"] = "not_a_number"  # noqa: S105
        config.reload()
        try:
            assert config.get("min_input_length") == 200  # default
        finally:
            del os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"]
            config.reload()
