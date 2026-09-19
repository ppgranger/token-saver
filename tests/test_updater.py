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

"""Verify update coordination with simulated remote and installer operations."""

import argparse
import io
import os
import subprocess
import sys
import tarfile
import types
import urllib.error
from unittest import mock

import pytest

import src
from src import cli
from src import updater


@pytest.fixture
def local_update(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData"))
    source = tmp_path / "source"
    source.mkdir()
    state = types.SimpleNamespace(
        home=home,
        source=source,
        fetch=mock.Mock(return_value=src.__version__),
        run=mock.Mock(),
        git=mock.Mock(),
        archive=mock.Mock(),
    )
    monkeypatch.setattr(
        updater.version_check, "_fetch_latest_version", state.fetch
    )
    monkeypatch.setattr(updater.subprocess, "run", state.run)
    monkeypatch.setattr(updater, "update_via_git", state.git)
    monkeypatch.setattr(updater, "update_via_tarball", state.archive)
    return state


def test_cli_delegates_with_explicit_source_location(monkeypatch):
    apply_update = mock.Mock()
    monkeypatch.setattr(updater, "update", apply_update)
    monkeypatch.setattr(cli, "_repo_dir", lambda: "isolated-source")
    cli.cmd_update(argparse.Namespace())
    apply_update.assert_called_once_with("isolated-source")


def test_marketplace_install_stops_before_remote_or_installer(
    local_update, capsys
):
    updater.update(str(local_update.source / "plugins" / "cache" / "plugin"))
    local_update.fetch.assert_not_called()
    local_update.run.assert_not_called()
    local_update.git.assert_not_called()
    local_update.archive.assert_not_called()
    assert capsys.readouterr().out == (
        f"token-saver v{src.__version__}\n"
        "This install is managed by the Claude Code plugin marketplace.\n"
        "Run '/plugin update token-saver' from within Claude Code to update.\n"
    )


@pytest.mark.parametrize("remote", [None, src.__version__, "0.0.0", "invalid"])
def test_absent_equal_older_or_invalid_release_still_refreshes(
    local_update, remote, capsys
):
    local_update.fetch.return_value = remote
    updater.update(str(local_update.source))
    local_update.fetch.assert_called_once_with(timeout=10)
    local_update.git.assert_not_called()
    local_update.archive.assert_not_called()
    local_update.run.assert_called_once_with(
        [
            sys.executable,
            str(local_update.source / "install.py"),
            "--target",
            "claude",
        ],
        check=True,
    )
    output = capsys.readouterr().out
    assert "Refreshing plugin install for: claude...\n" in output
    assert output.endswith(f"Done. Running v{src.__version__}.\n")


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError(
            "https://example.invalid",
            503,
            "synthetic-private-update-detail",
            {},
            None,
        ),
        urllib.error.URLError("synthetic-private-update-detail"),
    ],
)
def test_remote_lookup_failure_preserves_local_refresh(
    local_update, error, capsys, caplog
):
    local_update.fetch.side_effect = error
    updater.update(str(local_update.source))
    local_update.run.assert_called_once()
    local_update.git.assert_not_called()
    local_update.archive.assert_not_called()
    output = capsys.readouterr()
    assert "continuing with local refresh" in output.out
    assert "synthetic-private-update-detail" not in (
        output.out + output.err + caplog.text
    )


@pytest.mark.parametrize("git_checkout", [False, True])
def test_new_release_updates_before_one_installer_refresh(
    local_update, git_checkout, capsys
):
    local_update.fetch.return_value = "99.0.0"
    if git_checkout:
        (local_update.source / ".git").mkdir()
    events = []
    local_update.git.side_effect = lambda *_: events.append("git")
    local_update.archive.side_effect = lambda *_: events.append("archive")
    local_update.run.side_effect = lambda *_args, **_kwargs: events.append(
        "install"
    )
    updater.update(str(local_update.source))
    selected = local_update.git if git_checkout else local_update.archive
    selected.assert_called_once_with(str(local_update.source), "99.0.0")
    assert events == ["git" if git_checkout else "archive", "install"]
    local_update.run.assert_called_once()
    assert capsys.readouterr().out.endswith("Done. Running v99.0.0.\n")


def test_installer_failure_propagates_and_never_reports_completion(
    local_update, capsys
):
    local_update.run.side_effect = subprocess.CalledProcessError(1, "fixture")
    with pytest.raises(subprocess.CalledProcessError):
        updater.update(str(local_update.source))
    assert "Done." not in capsys.readouterr().out
    local_update.run.assert_called_once()


@pytest.mark.parametrize(
    ("claude", "antigravity", "expected"),
    [
        (False, False, "claude"),
        (True, False, "claude"),
        (False, True, "antigravity"),
        (True, True, "both"),
    ],
)
def test_target_detection_uses_only_the_temporary_profile(
    local_update, claude, antigravity, expected
):
    home = local_update.home
    if os.name == "nt":
        claude_dir = home / "AppData" / "claude"
        gemini_dir = home / "AppData" / "gemini"
    else:
        claude_dir = home / ".claude"
        gemini_dir = home / ".gemini"
    if claude:
        (claude_dir / "plugins" / "token-saver").mkdir(parents=True)
    if antigravity:
        (gemini_dir / "antigravity-cli" / "plugins" / "token-saver").mkdir(
            parents=True
        )
    assert updater.detect_installed_targets() == expected


@pytest.mark.parametrize("merge_statuses", [(0,), (1, 0), (1, 1)])
def test_git_tag_fallback_keeps_existing_commands_and_order(
    tmp_path, monkeypatch, merge_statuses
):
    statuses = [0, *merge_statuses]
    if merge_statuses == (1, 1):
        statuses.append(0)
    run = mock.Mock(
        side_effect=[
            types.SimpleNamespace(returncode=code) for code in statuses
        ]
    )
    monkeypatch.setattr(updater.subprocess, "run", run)
    source = str(tmp_path)
    updater.update_via_git(source, "99.0.0")
    expected = [
        mock.call(
            ["git", "-C", source, "fetch", "--tags", "origin"], check=True
        )
    ]
    for tag in ("v99.0.0", "99.0.0")[: len(merge_statuses)]:
        expected.append(
            mock.call(
                ["git", "-C", source, "merge", tag, "--ff-only"],
                capture_output=True,
                check=False,
            )
        )
    if merge_statuses == (1, 1):
        expected.append(
            mock.call(
                ["git", "-C", source, "pull", "origin", "main"], check=True
            )
        )
    assert run.call_args_list == expected


def _release_archive():
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name in ("src/new.py", "install.py", "README.md"):
            content = b"release fixture\n"
            member = tarfile.TarInfo(f"token-saver-99.0.0/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return payload.getvalue()


def test_archive_falls_back_on_404_and_overlays_only_known_paths(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src" / "old.py").write_text("old", encoding="utf-8")
    (source / ".git").mkdir()
    (source / "claude").mkdir()
    config = source / ".token-saver.json"
    config.write_text("{}", encoding="utf-8")
    download = mock.Mock(
        side_effect=[
            urllib.error.HTTPError(
                "https://example.invalid", 404, "missing", {}, None
            ),
            io.BytesIO(_release_archive()),
        ]
    )
    monkeypatch.setattr(updater.urllib.request, "urlopen", download)
    updater.update_via_tarball(str(source), "99.0.0")
    urls = [call.args[0].full_url for call in download.call_args_list]
    assert urls == [
        "https://github.com/ppgranger/token-saver/archive/refs/tags/v99.0.0.tar.gz",
        "https://github.com/ppgranger/token-saver/archive/refs/tags/99.0.0.tar.gz",
    ]
    assert (source / "src" / "new.py").read_text(encoding="utf-8") == (
        "release fixture\n"
    )
    assert not (source / "src" / "old.py").exists()
    assert not (source / "README.md").exists()
    assert not (source / "claude").exists()
    assert (source / ".git").is_dir()
    assert config.read_text(encoding="utf-8") == "{}"
    assert "Files updated from tarball." in capsys.readouterr().out


def test_archive_rejects_escaping_member_before_legacy_extraction(tmp_path):
    archive = mock.Mock()
    archive.extractall.side_effect = TypeError("filter unavailable")
    archive.getmembers.return_value = [tarfile.TarInfo("../outside.txt")]
    with pytest.raises(RuntimeError, match="Unsafe path"):
        updater.safe_extractall(archive, str(tmp_path))
    archive.extractall.assert_called_once_with(str(tmp_path), filter="data")
