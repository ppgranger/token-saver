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
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
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
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
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
        config_file.write_text("{ invalid json !!!", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        # Defaults still apply
        assert config.get("max_diff_hunk_lines") == 50

    def test_config_source_tracking(self, tmp_path, monkeypatch):
        """Test that _config_source tracks where values come from."""
        project_config = {"max_log_entries": 99}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        source = config.get("_config_source")
        assert source is not None
        assert source["min_input_length"] == "default"
        assert "project:" in source["max_log_entries"]

    def test_type_mismatch_falls_back_to_default(self, tmp_path, monkeypatch):
        """A wrong-typed file value must not reach downstream arithmetic."""
        project_config = {"max_chain_depth": "deep", "wrap_timeout": [1, 2]}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        # Uncoercible values are rejected; defaults survive (ints, not strings).
        assert config.get("max_chain_depth") == 3
        assert config.get("wrap_timeout") == 300
        assert isinstance(config.get("max_chain_depth"), int)

    def test_numeric_string_coerced(self, tmp_path, monkeypatch):
        """Numeric strings in file config are coerced to the default's type."""
        project_config = {"wrap_timeout": "120", "min_compression_ratio": "0.25"}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("wrap_timeout") == 120
        assert isinstance(config.get("wrap_timeout"), int)
        assert config.get("min_compression_ratio") == 0.25

    def test_unknown_file_key_ignored(self, tmp_path, monkeypatch):
        """Typo'd / unknown keys in file config are dropped."""
        project_config = {"max_diff_hunkk_lines": 999}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("max_diff_hunkk_lines") is None
        assert config.get("max_diff_hunk_lines") == 50


class TestProjectConfigForbiddenKeys:
    """A project-level .token-saver.json is discovered just by cd-ing into a
    directory — untrusted input.  user_processors_dir is arbitrary code
    execution (discover_processors() imports every .py file in it, on every
    Bash command); disabled_processors/redaction_allowlist can silently turn
    off the secret-redaction safety net.  None of the three may be set from
    there, regardless of type-correctness."""

    def setup_method(self):
        config.reload()

    def teardown_method(self):
        config.reload()

    def test_user_processors_dir_ignored_from_project_config(self, tmp_path, monkeypatch):
        evil_dir = tmp_path / "evil"
        evil_dir.mkdir()
        project_config = {"user_processors_dir": str(evil_dir)}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("user_processors_dir") == ""

    def test_disabled_processors_ignored_from_project_config(self, tmp_path, monkeypatch):
        project_config = {"disabled_processors": ["generic", "git"]}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("disabled_processors") == []

    def test_redaction_allowlist_ignored_from_project_config(self, tmp_path, monkeypatch):
        project_config = {"redaction_allowlist": ["*"]}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("redaction_allowlist") == []

    def test_other_keys_still_apply_from_project_config(self, tmp_path, monkeypatch):
        """The forbidden-key filter must not become a blanket project-config
        distrust — everything else still works exactly as before."""
        project_config = {
            "user_processors_dir": "/tmp/evil",
            "max_diff_hunk_lines": 250,
        }
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config.reload()

        assert config.get("user_processors_dir") == ""
        assert config.get("max_diff_hunk_lines") == 250

    def test_forbidden_keys_still_apply_from_global_config(self, tmp_path, monkeypatch):
        """The global ~/.token-saver/config.json is trusted (the user wrote
        it themselves) — only the project-discovered file is restricted."""
        from src import data_dir

        global_dir = data_dir()
        os.makedirs(global_dir, exist_ok=True)
        global_config_path = os.path.join(global_dir, "config.json")
        had_existing = os.path.exists(global_config_path)
        existing_content = None
        if had_existing:
            with open(global_config_path, encoding="utf-8") as f:
                existing_content = f.read()
        try:
            with open(global_config_path, "w", encoding="utf-8") as f:
                json.dump({"disabled_processors": ["git"]}, f)
            monkeypatch.chdir(tmp_path)  # no project .token-saver.json here
            config.reload()
            assert config.get("disabled_processors") == ["git"]
        finally:
            if had_existing:
                with open(global_config_path, "w", encoding="utf-8") as f:
                    f.write(existing_content)
            else:
                os.remove(global_config_path)
            config.reload()

    def test_env_var_still_applies_forbidden_keys(self, tmp_path, monkeypatch):
        """Env vars are trusted too — the restriction is specifically about
        the auto-discovered project file, not the key itself."""
        project_config = {"disabled_processors": ["git"]}
        config_file = tmp_path / ".token-saver.json"
        config_file.write_text(json.dumps(project_config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TOKEN_SAVER_DISABLED_PROCESSORS", "docker")
        config.reload()

        # Project config's value is dropped; env var (trusted) still wins.
        assert config.get("disabled_processors") == ["docker"]
