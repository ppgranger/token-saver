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

"""Exercise routing independently of registry discovery and hook protocols."""

import os
import pathlib
import subprocess
import sys
from unittest import mock

import pytest

from src import command_policy


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status", True),
        ("/usr/bin/git status", True),
        ("git log | head -20", True),
        ("cd /project && git status", True),
        ("echo start; git status", True),
        ("sudo git status", False),
        ("git status > output.txt", False),
        ("git status &", False),
        ("git status || echo recover", False),
        ("git status\nrm file", False),
        ("git status && python.exe -i", False),
        ("git status && 'C:/Program Files/Python/python.exe'", False),
        ("git status | sed -n 1p", False),
        ("git status $(echo filename)", False),
        ("cat notes.txt", False),
        ("", False),
    ],
)
def test_explicit_inventory_uses_same_evaluator_for_decision_and_explanation(
    command, expected
):
    policy = command_policy.CommandPolicy([r"^git\s+(status|log)\b"])
    decision = policy.explain_decision(command)
    assert policy.is_compressible(command) is expected
    assert decision["compressible"] is expected
    assert decision["command"] == command
    assert set(decision) == {
        "command",
        "compressible",
        "reason",
        "excluded_by",
        "matched_patterns",
        "is_chain",
    }


def test_processor_inventories_are_independent_and_extend_without_hooks():
    first = command_policy.CommandPolicy([r"^mytool\s+check\b"])
    second = command_policy.CommandPolicy([r"^different\s+check\b"])
    assert first.is_compressible("mytool check")
    assert not first.is_compressible("different check")
    assert second.is_compressible("different check")
    assert not second.is_compressible("mytool check")
    assert not first.is_compressible("sudo mytool check")


def test_broken_registry_disables_default_policy_without_exception_details(
    caplog,
):
    command_policy.default_policy.cache_clear()
    try:
        with mock.patch(
            "src.processors.collect_hook_patterns",
            side_effect=RuntimeError("private registry data"),
        ):
            assert not command_policy.is_compressible("git status")
            assert not command_policy.explain_decision("git status")[
                "compressible"
            ]
        assert "compression disabled" in caplog.text
        assert "private registry data" not in caplog.text
    finally:
        command_policy.default_policy.cache_clear()


def test_injected_policy_import_does_not_load_plugins_hooks_or_write_profile(
    tmp_path,
):
    repo = pathlib.Path(__file__).resolve().parent.parent
    profile = tmp_path / "profile"
    profile.mkdir()
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("TOKEN_SAVER_"):
            environment.pop(name)
    environment.update(
        HOME=str(profile), USERPROFILE=str(profile), APPDATA=str(profile)
    )
    program = "\n".join(
        [
            "import sys",
            "sys.path.insert(0, sys.argv[1])",
            "from src import command_policy",
            "policy = command_policy.CommandPolicy([r'^git\\b'])",
            "assert policy.is_compressible('git status')",
            "assert 'src.processors' not in sys.modules",
            "assert 'scripts.hook_pretool' not in sys.modules",
            "assert 'src.core' not in sys.modules",
        ]
    )
    result = subprocess.run(  # noqa: S603 — fixed, isolated import probe.
        [sys.executable, "-c", program, str(repo)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not list(profile.rglob("*"))
