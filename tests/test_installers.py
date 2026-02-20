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
