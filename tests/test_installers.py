"""Tests for installer utility functions: migration, version stamping, CLI/core install."""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from installers.common import (
    _read_version,
    install_cli,
    install_core,
    migrate_from_legacy,
    stamp_version,
    uninstall_cli,
    uninstall_core,
)


class TestReadVersion:
    def test_reads_current_version(self):
        from src import __version__

        assert _read_version() == __version__

    def test_version_is_valid_semver(self):
        version = _read_version()
        parts = version.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()


class TestStampVersion:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_stamps_version_into_json(self):
        manifest_path = os.path.join(self.tmp_dir, "plugin.json")
        with open(manifest_path, "w") as f:
            json.dump({"name": "test", "version": "0.0.0"}, f)

        stamp_version(self.tmp_dir, ["plugin.json"])

        with open(manifest_path) as f:
            data = json.load(f)
        assert data["version"] == _read_version()
        assert data["name"] == "test"

    def test_skips_symlinked_manifest(self):
        # Create a real file and a symlink to it
        real_path = os.path.join(self.tmp_dir, "real.json")
        with open(real_path, "w") as f:
            json.dump({"version": "0.0.0"}, f)

        link_dir = os.path.join(self.tmp_dir, "linked")
        os.makedirs(link_dir)
        link_path = os.path.join(link_dir, "plugin.json")
        os.symlink(real_path, link_path)

        stamp_version(link_dir, ["plugin.json"])

        # Original should NOT have been stamped (symlink was skipped)
        with open(real_path) as f:
            data = json.load(f)
        assert data["version"] == "0.0.0"

    def test_skips_missing_manifest(self):
        # Should not raise
        stamp_version(self.tmp_dir, ["nonexistent.json"])

    def test_stamps_marketplace_plugin_entries(self):
        """stamp_version must update version inside plugins[] array."""
        manifest_path = os.path.join(self.tmp_dir, "marketplace.json")
        with open(manifest_path, "w") as f:
            json.dump(
                {
                    "name": "test-marketplace",
                    "plugins": [
                        {"name": "my-plugin", "version": "1.0.0", "source": "./"},
                    ],
                },
                f,
            )

        stamp_version(self.tmp_dir, ["marketplace.json"])

        with open(manifest_path) as f:
            data = json.load(f)
        # The nested version must be stamped
        assert data["plugins"][0]["version"] == _read_version()
        # No spurious top-level version should be added
        assert "version" not in data

    def test_stamps_both_top_level_and_nested(self):
        """If a file has both top-level version AND plugins[], stamp both."""
        manifest_path = os.path.join(self.tmp_dir, "hybrid.json")
        with open(manifest_path, "w") as f:
            json.dump(
                {
                    "name": "hybrid",
                    "version": "0.0.0",
                    "plugins": [
                        {"name": "p1", "version": "0.0.0"},
                    ],
                },
                f,
            )

        stamp_version(self.tmp_dir, ["hybrid.json"])

        with open(manifest_path) as f:
            data = json.load(f)
        assert data["version"] == _read_version()
        assert data["plugins"][0]["version"] == _read_version()


class TestMigrateFromLegacy:
    def setup_method(self):
        self.tmp_home = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def test_removes_legacy_claude_dir(self):
        legacy_dir = os.path.join(self.tmp_home, ".claude", "plugins", "token-saving")
        os.makedirs(legacy_dir)
        # Write a dummy file to prove it gets removed
        with open(os.path.join(legacy_dir, "dummy.txt"), "w") as f:
            f.write("old")

        with mock.patch("installers.common.home", return_value=self.tmp_home):
            found = migrate_from_legacy()

        assert found is True
        assert not os.path.exists(legacy_dir)

    def test_removes_legacy_gemini_dir(self):
        legacy_dir = os.path.join(self.tmp_home, ".gemini", "extensions", "token-saving")
        os.makedirs(legacy_dir)

        with mock.patch("installers.common.home", return_value=self.tmp_home):
            found = migrate_from_legacy()

        assert found is True
        assert not os.path.exists(legacy_dir)

    def test_removes_legacy_data_dir(self):
        legacy_dir = os.path.join(self.tmp_home, ".token-saving")
        os.makedirs(legacy_dir)

        with mock.patch("installers.common.home", return_value=self.tmp_home):
            found = migrate_from_legacy()

        assert found is True
        assert not os.path.exists(legacy_dir)

    def test_cleans_legacy_hooks_from_settings(self):
        settings_dir = os.path.join(self.tmp_home, ".claude")
        os.makedirs(settings_dir)
        settings_path = os.path.join(settings_dir, "settings.json")

        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 /old/token-saving/claude/hook_pretool.py",
                            }
                        ],
                    },
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 /new/token-saver/claude/hook_pretool.py",
                            }
                        ],
                    },
                ],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        with mock.patch("installers.common.home", return_value=self.tmp_home):
            found = migrate_from_legacy()

        assert found is True
        with open(settings_path) as f:
            result = json.load(f)
        # Only the token-saver hook should remain
        assert len(result["hooks"]["PreToolUse"]) == 1
        assert "token-saver" in json.dumps(result["hooks"]["PreToolUse"][0])

    def test_noop_when_nothing_legacy(self):
        with mock.patch("installers.common.home", return_value=self.tmp_home):
            found = migrate_from_legacy()

        assert found is False

    def test_survives_malformed_hooks_in_settings(self):
        """settings.json with non-dict hooks value should not crash."""
        settings_dir = os.path.join(self.tmp_home, ".claude")
        os.makedirs(settings_dir)
        settings_path = os.path.join(settings_dir, "settings.json")

        # hooks is a string instead of a dict
        with open(settings_path, "w") as f:
            json.dump({"hooks": "invalid"}, f)

        with mock.patch("installers.common.home", return_value=self.tmp_home):
            # Should not raise
            found = migrate_from_legacy()

        assert found is False


class TestInstallCli:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copies_cli_script(self):
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=False)

        dst = os.path.join(self.tmp_dir, "token-saver")
        assert os.path.exists(dst)
        assert os.access(dst, os.X_OK)

    def test_symlinks_cli_script(self):
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=True)

        dst = os.path.join(self.tmp_dir, "token-saver")
        assert os.path.islink(dst)

    def test_uninstall_removes_cli(self):
        # First install
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=False)

        dst = os.path.join(self.tmp_dir, "token-saver")
        assert os.path.exists(dst)

        # Then uninstall
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            uninstall_cli()

        assert not os.path.exists(dst)

    def test_uninstall_noop_when_missing(self):
        # Should not raise
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            uninstall_cli()

    def test_install_overwrites_existing(self):
        dst = os.path.join(self.tmp_dir, "token-saver")
        with open(dst, "w") as f:
            f.write("old content")

        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=False)

        with open(dst) as f:
            content = f.read()
        assert "old content" not in content

    def test_copy_does_not_corrupt_symlink_target(self):
        """Switching from --link to copy should not overwrite the original source."""
        # First install with symlink
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=True)

        dst = os.path.join(self.tmp_dir, "token-saver")
        assert os.path.islink(dst)
        target_before = os.path.realpath(dst)
        with open(target_before) as f:
            original_content = f.read()

        # Reinstall with copy — should NOT overwrite the symlink target
        with mock.patch("installers.common._cli_install_dir", return_value=self.tmp_dir):
            install_cli(use_symlink=False)

        assert not os.path.islink(dst)  # should be a real file now
        with open(target_before) as f:
            assert f.read() == original_content  # original source untouched


class TestInstallCore:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copies_core_files(self):
        with mock.patch("installers.common.token_saver_data_dir", return_value=self.tmp_dir):
            install_core(use_symlink=False)

        # Verify key files exist
        assert os.path.isfile(os.path.join(self.tmp_dir, "src", "cli.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "src", "__init__.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "install.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "installers", "common.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "bin", "token-saver"))
        # New v2 files
        assert os.path.isfile(os.path.join(self.tmp_dir, ".claude-plugin", "plugin.json"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "hooks", "hooks.json"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "scripts", "hook_pretool.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "scripts", "wrap.py"))
        assert os.path.isfile(os.path.join(self.tmp_dir, "scripts", "__init__.py"))

    def test_bin_is_executable(self):
        with mock.patch("installers.common.token_saver_data_dir", return_value=self.tmp_dir):
            install_core(use_symlink=False)

        bin_path = os.path.join(self.tmp_dir, "bin", "token-saver")
        assert os.access(bin_path, os.X_OK)

    def test_uninstall_core_removes_files_keeps_db(self):
        # Simulate a DB file that should survive
        os.makedirs(self.tmp_dir, exist_ok=True)
        db_path = os.path.join(self.tmp_dir, "savings.db")
        with open(db_path, "w") as f:
            f.write("database")

        with mock.patch("installers.common.token_saver_data_dir", return_value=self.tmp_dir):
            install_core(use_symlink=False)
            uninstall_core()

        # Core files should be gone
        assert not os.path.exists(os.path.join(self.tmp_dir, "src", "cli.py"))
        assert not os.path.exists(os.path.join(self.tmp_dir, "install.py"))
        # DB should still be there
        assert os.path.isfile(db_path)

    def test_uninstall_core_cleans_empty_parent_dirs(self):
        """Verify that nested empty directories (e.g. src/) are removed after children."""
        with mock.patch("installers.common.token_saver_data_dir", return_value=self.tmp_dir):
            install_core(use_symlink=False)
            uninstall_core()

        # src/ and src/processors/ should both be removed (empty after file deletion)
        assert not os.path.exists(os.path.join(self.tmp_dir, "src", "processors"))
        assert not os.path.exists(os.path.join(self.tmp_dir, "src"))
        # data_dir itself should still exist
        assert os.path.isdir(self.tmp_dir)

    def test_cleans_legacy_claude_directory(self):
        """install_core should remove legacy claude/ subdirectory from data dir."""
        legacy_claude = os.path.join(self.tmp_dir, "claude")
        os.makedirs(legacy_claude)
        with open(os.path.join(legacy_claude, "hook_pretool.py"), "w") as f:
            f.write("# old hook")

        with mock.patch("installers.common.token_saver_data_dir", return_value=self.tmp_dir):
            install_core(use_symlink=False)

        assert not os.path.exists(legacy_claude)


class TestMigrateFromV1:
    """Tests for v1.x -> v2.0 migration in the Claude installer."""

    def setup_method(self):
        self.tmp_home = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def _settings_dir(self):
        return os.path.join(self.tmp_home, ".claude")

    def _settings_path(self):
        return os.path.join(self._settings_dir(), "settings.json")

    def _write_settings(self, settings):
        os.makedirs(self._settings_dir(), exist_ok=True)
        with open(self._settings_path(), "w") as f:
            json.dump(settings, f)

    def _read_settings(self):
        with open(self._settings_path()) as f:
            return json.load(f)

    def test_removes_v1_hooks_from_settings(self):
        from installers.claude import _migrate_from_v1

        self._write_settings(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /home/user/.claude/plugins/"
                                    "token-saver/claude/hook_pretool.py",
                                }
                            ],
                        }
                    ],
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /home/user/.claude/plugins/"
                                    "token-saver/src/hook_session.py",
                                }
                            ],
                        }
                    ],
                }
            }
        )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            result = _migrate_from_v1()

        assert result is True
        settings = self._read_settings()
        assert "hooks" not in settings

    def test_removes_v1_session_hooks_from_settings(self):
        from installers.claude import _migrate_from_v1

        self._write_settings(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /path/to/src/hook_session.py",
                                }
                            ],
                        }
                    ],
                }
            }
        )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            result = _migrate_from_v1()

        assert result is True
        settings = self._read_settings()
        assert "hooks" not in settings

    def test_removes_legacy_v1_plugin_directory(self):
        from installers.claude import _migrate_from_v1

        old_dir = os.path.join(self._settings_dir(), "plugins", "token-saver")
        claude_subdir = os.path.join(old_dir, "claude")
        os.makedirs(claude_subdir)
        with open(os.path.join(claude_subdir, "hook_pretool.py"), "w") as f:
            f.write("# old")

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            result = _migrate_from_v1()

        assert result is True
        assert not os.path.exists(old_dir)

    def test_idempotent(self):
        from installers.claude import _migrate_from_v1

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            result1 = _migrate_from_v1()
            result2 = _migrate_from_v1()

        assert result1 is False
        assert result2 is False

    def test_fresh_install_returns_false(self):
        from installers.claude import _migrate_from_v1

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            result = _migrate_from_v1()

        assert result is False


class TestRegisterPlugin:
    """Tests for native plugin registration."""

    def setup_method(self):
        self.tmp_home = tempfile.mkdtemp()
        self.tmp_target = tempfile.mkdtemp()  # cache dir (plugin runtime)
        self.tmp_marketplace = tempfile.mkdtemp()  # marketplace dir (discovery)

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)
        shutil.rmtree(self.tmp_target, ignore_errors=True)
        shutil.rmtree(self.tmp_marketplace, ignore_errors=True)

    def _settings_dir(self):
        return os.path.join(self.tmp_home, ".claude")

    def _settings_path(self):
        return os.path.join(self._settings_dir(), "settings.json")

    def _installed_plugins_path(self):
        return os.path.join(
            self._settings_dir(),
            "plugins",
            "installed_plugins.json",
        )

    def _known_marketplaces_path(self):
        return os.path.join(
            self._settings_dir(),
            "plugins",
            "known_marketplaces.json",
        )

    def test_registers_marketplace(self):
        from installers.claude import _register_plugin

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(self._known_marketplaces_path()) as f:
            known = json.load(f)
        assert "token-saver-marketplace" in known
        entry = known["token-saver-marketplace"]
        assert entry["source"]["source"] == "github"
        assert entry["source"]["repo"] == "ppgranger/token-saver"
        assert entry["source"]["ref"] == "production"
        assert entry["installLocation"] == self.tmp_marketplace

    def test_registers_in_installed_plugins_v2_format(self):
        from installers.claude import _register_plugin

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(self._installed_plugins_path()) as f:
            data = json.load(f)
        assert data["version"] == 2
        key = "token-saver@token-saver-marketplace"
        assert key in data["plugins"]
        entries = data["plugins"][key]
        assert len(entries) == 1
        assert entries[0]["version"] == "2.0.0"
        assert entries[0]["installPath"] == self.tmp_target
        assert entries[0]["scope"] == "user"

    def test_enables_in_settings(self):
        from installers.claude import _register_plugin

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(self._settings_path()) as f:
            settings = json.load(f)
        key = "token-saver@token-saver-marketplace"
        assert settings["enabledPlugins"][key] is True

    def test_no_duplicates_on_reregistration(self):
        from installers.claude import _register_plugin

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(self._installed_plugins_path()) as f:
            data = json.load(f)
        key = "token-saver@token-saver-marketplace"
        assert len(data["plugins"][key]) == 1

    def test_preserves_existing_marketplaces(self):
        from installers.claude import _register_plugin

        # Pre-populate with another marketplace
        km_path = self._known_marketplaces_path()
        os.makedirs(os.path.dirname(km_path), exist_ok=True)
        with open(km_path, "w") as f:
            json.dump(
                {
                    "claude-plugins-official": {
                        "source": {"source": "github", "repo": "anthropics/x"},
                        "installLocation": "/tmp/x",
                    },
                },
                f,
            )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(km_path) as f:
            known = json.load(f)
        assert "claude-plugins-official" in known
        assert "token-saver-marketplace" in known

    def test_preserves_existing_v2_plugins(self):
        from installers.claude import _register_plugin

        # Pre-populate with another plugin in v2 format
        plugins_path = self._installed_plugins_path()
        os.makedirs(os.path.dirname(plugins_path), exist_ok=True)
        with open(plugins_path, "w") as f:
            json.dump(
                {
                    "version": 2,
                    "plugins": {
                        "other@official": [{"scope": "user", "version": "1.0"}],
                    },
                },
                f,
            )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _register_plugin(self.tmp_marketplace, self.tmp_target, "2.0.0")

        with open(plugins_path) as f:
            data = json.load(f)
        assert "other@official" in data["plugins"]
        assert "token-saver@token-saver-marketplace" in data["plugins"]


class TestUnregisterPlugin:
    """Tests for native plugin unregistration."""

    def setup_method(self):
        self.tmp_home = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def _settings_dir(self):
        return os.path.join(self.tmp_home, ".claude")

    def _settings_path(self):
        return os.path.join(self._settings_dir(), "settings.json")

    def _installed_plugins_path(self):
        return os.path.join(
            self._settings_dir(),
            "plugins",
            "installed_plugins.json",
        )

    def _known_marketplaces_path(self):
        return os.path.join(
            self._settings_dir(),
            "plugins",
            "known_marketplaces.json",
        )

    def test_removes_from_all_files_v2(self):
        from installers.claude import _unregister_plugin

        plugins_dir = os.path.join(self._settings_dir(), "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        # Set up installed state in v2 format
        with open(self._installed_plugins_path(), "w") as f:
            json.dump(
                {
                    "version": 2,
                    "plugins": {
                        "token-saver@token-saver-marketplace": [
                            {"scope": "user", "version": "2.0.0"},
                        ],
                    },
                },
                f,
            )

        with open(self._known_marketplaces_path(), "w") as f:
            json.dump(
                {
                    "token-saver-marketplace": {
                        "source": {"source": "github", "repo": "ppgranger/token-saver"},
                    },
                },
                f,
            )

        os.makedirs(os.path.dirname(self._settings_path()), exist_ok=True)
        with open(self._settings_path(), "w") as f:
            json.dump(
                {
                    "enabledPlugins": {
                        "token-saver@token-saver-marketplace": True,
                    },
                },
                f,
            )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _unregister_plugin()

        with open(self._installed_plugins_path()) as f:
            data = json.load(f)
        assert "token-saver@token-saver-marketplace" not in data["plugins"]

        with open(self._known_marketplaces_path()) as f:
            assert "token-saver-marketplace" not in json.load(f)

        with open(self._settings_path()) as f:
            assert "enabledPlugins" not in json.load(f)

    def test_removes_from_v1_format(self):
        """Unregister handles our old v1 array format in installed_plugins."""
        from installers.claude import _unregister_plugin

        plugins_dir = os.path.join(self._settings_dir(), "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        with open(self._installed_plugins_path(), "w") as f:
            json.dump(
                [
                    {
                        "name": "token-saver",
                        "marketplace": "token-saver-marketplace",
                    }
                ],
                f,
            )

        os.makedirs(os.path.dirname(self._settings_path()), exist_ok=True)
        with open(self._settings_path(), "w") as f:
            json.dump(
                {
                    "enabledPlugins": {
                        "token-saver@token-saver-marketplace": True,
                    },
                },
                f,
            )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _unregister_plugin()

        with open(self._installed_plugins_path()) as f:
            assert len(json.load(f)) == 0

    def test_cleans_legacy_hooks(self):
        from installers.claude import _unregister_plugin

        os.makedirs(os.path.dirname(self._settings_path()), exist_ok=True)
        with open(self._settings_path(), "w") as f:
            json.dump(
                {
                    "enabledPlugins": {
                        "token-saver@token-saver-marketplace": True,
                    },
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 /p/hook_pretool.py",
                                    },
                                ],
                            }
                        ],
                    },
                },
                f,
            )

        with mock.patch("installers.claude.home", return_value=self.tmp_home):
            _unregister_plugin()

        with open(self._settings_path()) as f:
            settings = json.load(f)
        assert "enabledPlugins" not in settings
        assert "hooks" not in settings


class TestPluginStructure:
    """Validate the plugin directory structure in the repo."""

    def _repo_root(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_plugin_json_valid(self):
        path = os.path.join(self._repo_root(), ".claude-plugin", "plugin.json")
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert "name" in data
        assert "version" in data
        assert "description" in data

    def test_marketplace_json_valid(self):
        path = os.path.join(self._repo_root(), ".claude-plugin", "marketplace.json")
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert "plugins" in data
        assert isinstance(data["plugins"], list)
        assert len(data["plugins"]) > 0

    def test_hooks_json_uses_plugin_root_var(self):
        path = os.path.join(self._repo_root(), "hooks", "hooks.json")
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        data = json.loads(content)
        # All command paths must use ${CLAUDE_PLUGIN_ROOT}, not absolute paths
        assert "${CLAUDE_PLUGIN_ROOT}" in content
        assert "/Users/" not in content
        assert "/home/" not in content
        # Verify structure: must have top-level "hooks" wrapper
        assert "hooks" in data
        hooks = data["hooks"]
        assert "PreToolUse" in hooks
        assert "SessionStart" in hooks

    def test_scripts_init_exists(self):
        path = os.path.join(self._repo_root(), "scripts", "__init__.py")
        assert os.path.isfile(path)

    def test_skill_exists(self):
        path = os.path.join(self._repo_root(), "skills", "token-saver-config", "SKILL.md")
        assert os.path.isfile(path)

    def test_command_exists(self):
        path = os.path.join(self._repo_root(), "commands", "token-saver-stats.md")
        assert os.path.isfile(path)

    def test_claude_directory_does_not_exist(self):
        path = os.path.join(self._repo_root(), "claude")
        assert not os.path.exists(path)

    def test_claude_md_exists(self):
        path = os.path.join(self._repo_root(), "CLAUDE.md")
        assert os.path.isfile(path)
