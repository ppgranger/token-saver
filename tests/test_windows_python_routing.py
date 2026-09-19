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

"""Keep Windows Python module routing aligned with shell exclusions."""

import pytest

from scripts import hook_pretool
from src import engine
from src.processors import generic
from src.processors import lint_output
from src.processors import test_output

_LAUNCHERS = (
    "python.exe",
    "C:/hostedtoolcache/windows/Python/3.12.10/x64/python.exe",
    "'C:/Program Files/Python/python.exe'",
    '"C:/Program Files/Python/python.exe"',
    "'/opt/python tools/python3.12'",
)

_PYTEST_OUTPUT = """==================== FAILURES ====================
____________________ test_value ____________________
    def test_value():
>       assert 1 == 2
E       assert 1 == 2

test_example.py:2: AssertionError
================ short test summary info ================
FAILED test_example.py::test_value - assert 1 == 2
==================== 1 failed in 0.01s ====================
"""


@pytest.mark.parametrize("launcher", _LAUNCHERS)
@pytest.mark.parametrize(
    ("arguments", "processor", "output", "family"),
    [
        (
            "-m pytest -vv",
            test_output.TestOutputProcessor,
            _PYTEST_OUTPUT,
            "pytest",
        ),
        (
            "-m ruff check .",
            lint_output.LintOutputProcessor,
            "example.py:1:1: F821 Undefined name `missing`\nFound 1 error.\n",
            "ruff",
        ),
    ],
)
def test_python_launcher_reaches_hook_and_diagnostics(
    launcher, arguments, processor, output, family
):
    command = f"{launcher} {arguments}"
    assert hook_pretool.is_compressible(command)
    assert hook_pretool.explain_decision(command)["compressible"]
    compressor = engine.CompressionEngine(
        processors=[processor(), generic.GenericProcessor()],
        settings={"enabled": True},
    )
    snapshot = compressor.diagnostics(command, output, exit_code=1)
    assert snapshot is not None
    assert snapshot.family == family
    assert len(snapshot.diagnostics) == 1


@pytest.mark.parametrize("launcher", _LAUNCHERS)
@pytest.mark.parametrize(
    "arguments",
    [
        "-i -m pytest",
        "--interactive -m pytest",
        "-ic 'print(1)'",
        "C:/token-saver/scripts/wrap.py 'pytest'",
        "-m pytest > result.txt",
        "-m pytest &",
        "-m pytest | sed -n 1p",
        "-m pytest $(echo tests)",
    ],
)
def test_python_launchers_retain_single_command_exclusions(launcher, arguments):
    command = f"{launcher} {arguments}"
    assert not hook_pretool.is_compressible(command)
    assert not hook_pretool.explain_decision(command)["compressible"]


@pytest.mark.parametrize("launcher", _LAUNCHERS)
@pytest.mark.parametrize(
    "arguments", ["", "-i script.py", "C:/token-saver/scripts/wrap.py pytest"]
)
def test_python_launchers_retain_chain_exclusions(launcher, arguments):
    command = f"git status && {launcher} {arguments}"
    assert not hook_pretool.is_compressible(command)
    assert not hook_pretool.explain_decision(command)["compressible"]
