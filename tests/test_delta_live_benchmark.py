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

"""Exercise real tools, wrapper exits and retrieval through the live example."""

import importlib.util
import json
import math
import os
import pathlib
import shlex
import subprocess
import sys
import types

import pytest

from examples import delta_live_benchmark

_REPOSITORY = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("family", ["pytest", "ruff"])
@pytest.mark.parametrize(
    ("platform", "executable", "expected"),
    [
        (
            "nt",
            r"C:\Program Files\Python\python.exe",
            "C:/Program Files/Python/python.exe",
        ),
        ("posix", "/opt/python's bin/python3", "/opt/python's bin/python3"),
    ],
)
def test_fixture_command_quotes_the_posix_shell_boundary(
    monkeypatch, family, platform, executable, expected
):
    monkeypatch.setattr(
        delta_live_benchmark, "os", types.SimpleNamespace(name=platform)
    )
    monkeypatch.setattr(
        delta_live_benchmark,
        "sys",
        types.SimpleNamespace(executable=executable),
    )
    command = delta_live_benchmark._fixture_command(family)
    assert shlex.split(command)[:3] == [expected, "-m", family]


@pytest.mark.skipif(
    importlib.util.find_spec("ruff") is None,
    reason="The live benchmark requires the Ruff development dependency",
)
def test_real_tool_lifecycles_and_retrieval_costs(tmp_path):
    environment = dict(os.environ)
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    result = subprocess.run(  # noqa: S603 — isolated generated fixture projects.
        [
            sys.executable,
            str(_REPOSITORY / "examples" / "delta_live_benchmark.py"),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert set(report["versions"]) == {"python", "pytest", "ruff"}
    for family, measurements in report["families"].items():
        assert measurements["wrapper_executions"] == 10
        assert [run["exit_code"] for run in measurements["runs"]] == [
            1,
            1,
            1,
            1,
            0,
        ]
        totals = measurements["totals"]
        for mode in ("ordinary", "delta"):
            sizes = [row[mode] for row in measurements["runs"]]
            assert totals[mode]["characters"] == sum(sizes)
            assert totals[mode]["estimated_tokens"] == sum(
                math.ceil(size / 4) for size in sizes
            )
        assert (
            totals["delta"]["characters"]
            < totals["delta_plus_targeted_read"]["characters"]
            < totals["delta_plus_complete_read"]["characters"]
        )
        if family == "pytest":
            # The generated test module records every collection; reads must
            # neither run it again nor replace any requested execution.
            assert measurements["pytest_executions"] == 10
    assert set(report["families"]) == {"pytest", "ruff"}
