"""Tests for the configuration system."""

import json
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
        assert config.get("min_input_length") == 1
        assert config.get("min_compression_ratio") == 0.0
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

    def test_default_disabled_processors(self, monkeypatch):
        for key in list(os.environ):
            if key.startswith("TOKEN_SAVER_"):
                monkeypatch.delenv(key)
        config.reload()
        assert config.get("disabled_processors") == []

    def test_env_override_list(self):
        os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"] = "git,docker"  # noqa: S105
        config.reload()
        try:
            assert config.get("disabled_processors") == ["git", "docker"]
        finally:
            del os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"]
            config.reload()

    def test_env_override_list_single_value(self):
        os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"] = "git"  # noqa: S105
        config.reload()
        try:
            assert config.get("disabled_processors") == ["git"]
        finally:
            del os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"]
            config.reload()

    def test_default_max_chain_depth(self, monkeypatch):
        for key in list(os.environ):
            if key.startswith("TOKEN_SAVER_"):
                monkeypatch.delenv(key)
        config.reload()
        assert config.get("max_chain_depth") == 3

    def test_env_override_list_empty_string(self):
        os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"] = ""
        config.reload()
        try:
            assert config.get("disabled_processors") == []
        finally:
            del os.environ["TOKEN_SAVER_DISABLED_PROCESSORS"]
            config.reload()

    def test_invalid_env_value_ignored(self):
        os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"] = "not_a_number"  # noqa: S105
        config.reload()
        try:
            assert config.get("min_input_length") == 1  # default
        finally:
            del os.environ["TOKEN_SAVER_MIN_INPUT_LENGTH"]
            config.reload()


class TestProjectConfig:
    def setup_method(self):
        config.reload()

    def teardown_method(self):
        config.reload()

    def test_project_config_overrides_global(self, tmp_path, monkeypatch):
        """Test that .token-saver.json in cwd overrides global defaults."""
        project_config = {"max_diff_hunk_lines": 300, "max_log_entries": 50}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config))
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("max_diff_hunk_lines") == 300
        assert config.get("max_log_entries") == 50
        # Non-overridden keys remain default
        assert config.get("min_input_length") == 1

    def test_parent_directory_walk_up(self, tmp_path, monkeypatch):
        """Test that config is found in parent directories."""
        project_config = {"generic_truncate_threshold": 1000}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config))
        subdir = tmp_path / "deep" / "nested" / "path"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        config.reload()

        assert config.get("generic_truncate_threshold") == 1000

    def test_missing_project_config_noop(self, tmp_path, monkeypatch):
        """Test that missing project config is a no-op."""
        monkeypatch.chdir(tmp_path)
        config.reload()

        # Defaults still apply
        assert config.get("max_diff_hunk_lines") == 50
        assert config.get("min_input_length") == 1

    def test_invalid_project_config_ignored(self, tmp_path, monkeypatch):
        """Test that invalid JSON in project config is silently ignored."""
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text("{ invalid json !!!")
        monkeypatch.chdir(tmp_path)
        config.reload()

        # Defaults still apply
        assert config.get("max_diff_hunk_lines") == 50

    def test_config_source_tracking(self, tmp_path, monkeypatch):
        """Test that _config_source tracks where values come from."""
        project_config = {"max_log_entries": 99}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config))
        monkeypatch.chdir(tmp_path)
        config.reload()

        source = config.get("_config_source")
        assert source is not None
        assert source["min_input_length"] == "default"
        assert "project:" in source["max_log_entries"]
