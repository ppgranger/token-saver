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

"""Behavior checks for the supplemental Python structural style rules."""

import pathlib
import sys

import pytest

from scripts import check_python_style


@pytest.mark.parametrize(
    "source",
    [
        "values = [x for x in first for y in second]",
        "values = {x for x in first for y in second}",
        "values = {x: y for x in first for y in second}",
        "values = (x for x in first for y in second)",
        "values = [x for x in first if x if ready]",
    ],
)
def test_rejects_multiple_comprehension_loops_or_filters(source, tmp_path):
    errors = check_python_style.check_source(
        source, tmp_path / "case.py", import_roots=(tmp_path,)
    )
    assert len(errors) == 1
    assert ":1: simple-comprehension:" in errors[0]


def test_accepts_simple_comprehensions_and_explicit_nested_loops(tmp_path):
    source = """
values = [x for x in first if x and ready]
mapping = {x: x.value for x in first}
unique = {x for x in first}
stream = (x for x in first)
for x in first:
    for y in second:
        values.append((x, y))
"""
    assert not check_python_style.check_source(
        source, tmp_path / "case.py", import_roots=(tmp_path,)
    )


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("from . import sibling", "absolute-import"),
        ("from ..package import sibling", "absolute-import"),
        ("from pathlib import Path", "module-import"),
        ("from package import public_function", "module-import"),
        ("from typing import *", "module-import"),
    ],
)
def test_rejects_member_relative_and_wildcard_imports(source, rule, tmp_path):
    errors = check_python_style.check_source(
        source, tmp_path / "case.py", import_roots=(tmp_path,)
    )
    assert len(errors) == 1
    assert f":1: {rule}:" in errors[0]


def test_accepts_typing_imports_and_ignores_code_in_fixture_strings(tmp_path):
    source = """
from __future__ import annotations
from typing import Any, Protocol
from typing_extensions import TypeAlias
from collections.abc import Iterable
import pathlib
fixture = "from pathlib import Path"
other = "[x for x in first for y in second]"
"""
    assert not check_python_style.check_source(
        source, tmp_path / "case.py", import_roots=(tmp_path,)
    )


def test_resolves_local_modules_without_importing_package_code(tmp_path):
    package = tmp_path / "untrusted_package"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise RuntimeError("package must not execute")', encoding="utf-8"
    )
    (package / "worker.py").write_text(
        'raise RuntimeError("module must not execute")', encoding="utf-8"
    )
    (package / "nested").mkdir()
    errors = check_python_style.check_source(
        "from untrusted_package import worker\n"
        "from untrusted_package import nested",
        tmp_path / "case.py",
        import_roots=(tmp_path,),
    )
    assert not errors
    assert "untrusted_package" not in sys.modules


def test_missing_imported_member_is_reported_even_when_package_exists(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "__init__.py").write_text("class Member: pass", encoding="utf-8")
    errors = check_python_style.check_source(
        "from package import Member",
        tmp_path / "case.py",
        import_roots=(tmp_path,),
    )
    assert len(errors) == 1
    assert "package.Member" in errors[0]


def test_collects_syntax_encoding_and_missing_path_failures(tmp_path):
    bad_syntax = tmp_path / "syntax.py"
    bad_syntax.write_text("for", encoding="utf-8")
    bad_encoding = tmp_path / "encoding.py"
    bad_encoding.write_bytes(b"\xff")
    errors = check_python_style.check_paths(
        [tmp_path, tmp_path / "missing"], import_roots=(tmp_path,)
    )
    assert len(errors) == 3
    assert any(": syntax:" in error for error in errors)
    assert any("cannot read UTF-8 source" in error for error in errors)
    assert any("path does not exist" in error for error in errors)


def test_checks_explicit_launcher_without_python_suffix(tmp_path):
    launcher = tmp_path / "launcher"
    launcher.write_text("from . import module", encoding="utf-8")
    errors = check_python_style.check_paths(
        [launcher], import_roots=(tmp_path,)
    )
    assert len(errors) == 1
    assert "absolute-import" in errors[0]


def test_main_checks_selected_files_and_returns_failing_status(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "case.py"
    source.write_text("from pathlib import Path", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_python_style", str(source)])
    assert check_python_style.main() == 1
    assert "module-import" in capsys.readouterr().out
    source.write_text("from urllib import parse", encoding="utf-8")
    assert check_python_style.main() == 0
    assert "checks passed" in capsys.readouterr().out


def test_repository_default_paths_are_not_relative_to_working_directory(
    tmp_path, monkeypatch
):
    captured_paths = []

    def capture(paths, *, import_roots):
        captured_paths.extend(paths)
        assert all(root.is_absolute() for root in import_roots)
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_python_style"])
    monkeypatch.setattr(check_python_style, "check_paths", capture)
    assert check_python_style.main() == 0
    assert all(path.is_absolute() for path in captured_paths)
    assert any(path.name == "token-saver" for path in captured_paths)
    assert pathlib.Path.cwd() == tmp_path
