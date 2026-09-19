#!/usr/bin/env python3
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

"""Measure real pytest/Ruff commands on generated, disposable fixture projects.

Run ``python3 examples/delta_live_benchmark.py`` with pytest and Ruff installed
in that interpreter. Add ``--json`` for machine-readable results. Each fixture
check runs ten times: five steps for ordinary compression and Delta. A separate
version probe identifies each tool.
These are controlled fixtures, not observations of real-world agent tasks.
All output characters, including retrieval hints, are counted. Request/tool
overhead, billed tokens, elapsed time and agent task success are not measured.
"""

import argparse
import json
import math
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

_REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
_STAGES = ("baseline", "repeat", "edit", "repeat edited", "passing")
_TEST_MODULE = """import json
import pathlib
import pytest

state = json.loads(pathlib.Path("state.json").read_text(encoding="utf-8"))
counter = pathlib.Path("executions.txt")
prior = counter.read_text(encoding="utf-8") if counter.exists() else ""
counter.write_text(prior + "x", encoding="utf-8")

@pytest.mark.parametrize("number", range(20))
def test_success(number):
    assert number >= 0

def test_payload():
    actual = list(range(40))
    actual[-1] = state["payload"]
    assert actual == list(range(40)), "payload diagnostic"

def test_status():
    actual = list(range(40))
    actual[-1] = state["status"]
    assert actual == list(range(40)), "status diagnostic"

def test_cache():
    actual = list(range(40))
    actual[-1] = state["cache"]
    assert actual == list(range(40)), "cache diagnostic"

def test_invoice():
    actual = list(range(40))
    actual[-1] = state["invoice"]
    assert actual == list(range(40)), "invoice diagnostic"
"""


def _environment(root: pathlib.Path, mode: str) -> dict[str, str]:
    """Isolate profiles, tool configuration and optional pytest plugins."""
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith(("TOKEN_SAVER_", "PYTEST_", "RUFF_")):
            environment.pop(name)
    profile = root / mode
    profile.mkdir()
    environment.update(
        HOME=str(profile),
        USERPROFILE=str(profile),
        APPDATA=str(profile),
        XDG_CONFIG_HOME=str(profile / "config"),
        XDG_DATA_HOME=str(profile / "data"),
        XDG_CACHE_HOME=str(profile / "cache"),
        TOKEN_SAVER_DB_DIR=str(profile / "data"),
        TOKEN_SAVER_ENABLED="true",  # noqa: S106 — feature switch.
        TOKEN_SAVER_DELTA_ENABLED=str(mode == "delta").lower(),
        TOKEN_SAVER_SESSION="live-benchmark",  # noqa: S106 — fixture ID.
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
        NO_COLOR="1",
        COLUMNS="100",
    )
    return environment


def _run(
    arguments: list[str], project: pathlib.Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Execute a fixed local command with a timeout and UTF-8 capture."""
    return subprocess.run(  # noqa: S603 — generated local fixture commands.
        arguments,
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _require(condition: bool, message: str) -> None:
    """Keep preservation and execution checks active under Python -O."""
    if not condition:
        raise RuntimeError(message)


def _write_stage(project: pathlib.Path, stage: int) -> None:
    """Create both tool fixtures with unchanged, changed and new failures."""
    state = {"payload": -1, "status": -1, "cache": -1, "invoice": 39}
    if stage >= 2:
        state.update(status=-2, cache=39, invoice=-1)
    if stage == 4:
        state = dict.fromkeys(state, 39)
    (project / "state.json").write_text(json.dumps(state), encoding="utf-8")
    source = []
    for name, value in state.items():
        expression = "0" if value == 39 else f"missing_{name}_{abs(value)}"
        source.extend([f"def {name}():", f"    return {expression}", ""])
    (project / "lint_fixture.py").write_text(
        "\n".join(source), encoding="utf-8"
    )


def _retrieval(
    output: str,
    family: str,
    project: pathlib.Path,
    environment: dict[str, str],
) -> dict[str, int]:
    """Read one repeated-run diagnostic and its entire retained snapshot."""
    match = re.search(r"delta show ([0-9a-f]{32})", output)
    _require(match is not None, f"{family}: missing Delta retrieval hint")
    diagnostic = (
        "test_fixture.py::test_payload"
        if family == "pytest"
        else "lint_fixture.py:2:12:F821"
    )
    command = [
        sys.executable,
        str(_REPOSITORY / "bin" / "token-saver"),
        "delta",
        "show",
        match[1],
    ]
    sizes = {}
    for label, extra in (
        ("targeted", ["--diagnostic", diagnostic]),
        ("complete", []),
    ):
        result = _run(command + extra, project, environment)
        _require(result.returncode == 0, f"{family}: {label} retrieval failed")
        expected = (
            'assert actual == list(range(40)), "payload diagnostic"'
            if family == "pytest"
            else "return missing_payload_1"
        )
        _require(expected in result.stdout, f"{family}: details were lost")
        sizes[label] = len(result.stdout) + len(result.stderr)
    return sizes


def _fixture_command(family: str) -> str:
    """Quote fixture arguments for the wrapper's POSIX shell on every OS."""
    arguments = (
        ["-m", "pytest", "-vv", "--color=no", "test_fixture.py"]
        if family == "pytest"
        else [
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--output-format",
            "full",
            "lint_fixture.py",
        ]
    )
    # Git Bash accepts drive-letter paths with slashes. Backslashes and spaces
    # must never be handed to this POSIX shell using Windows argv quoting.
    executable = (
        sys.executable.replace("\\", "/") if os.name == "nt" else sys.executable
    )
    return shlex.join([executable, *arguments])


def _measure_family(
    family: str, root: pathlib.Path, environments: dict[str, dict[str, str]]
) -> dict:
    """Compare five actual command executions per mode and verify evidence."""
    project = root / family
    project.mkdir()
    (project / ".token-saver.json").write_text("{}\n", encoding="utf-8")
    (project / "test_fixture.py").write_text(_TEST_MODULE, encoding="utf-8")
    # An explicit root prevents pytest from discovering parent configuration.
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    wrapper = [
        sys.executable,
        str(_REPOSITORY / "scripts" / "wrap.py"),
        _fixture_command(family),
    ]
    rows = []
    retrieval = {}
    wrapper_executions = 0
    for index, stage in enumerate(_STAGES):
        _write_stage(project, index)
        row = {"stage": stage, "exit_code": 0 if index == 4 else 1}
        for mode, environment in environments.items():
            result = _run(wrapper, project, environment)
            wrapper_executions += 1
            _require(
                result.returncode == row["exit_code"],
                f"{family}/{stage}/{mode}: unexpected exit status",
            )
            output = result.stdout + result.stderr
            row[mode] = len(output)
            if mode != "delta":
                continue
            if index == 1:
                _require("UNCHANGED" in output, f"{family}: no comparison")
                retrieval = _retrieval(output, family, project, environment)
            if index == 2:
                expected = (
                    "invoice diagnostic"
                    if family == "pytest"
                    else "missing_invoice_1"
                )
                _require(expected in output, f"{family}: new failure lost")
                expected = (
                    "At index 39 diff: -2 != 39"
                    if family == "pytest"
                    else "return missing_status_2"
                )
                _require(expected in output, f"{family}: changed failure lost")
            if index == 4:
                _require("UNCHANGED" not in output, f"{family}: stale failure")
                expected = (
                    "24 passed" if family == "pytest" else "All checks passed!"
                )
                _require(expected in output, f"{family}: passing result lost")
        rows.append(row)
    executions = None
    if family == "pytest":
        executions = len(
            (project / "executions.txt").read_text(encoding="utf-8")
        )
        _require(executions == 10, "pytest was rerun or skipped")
    totals = {}
    for mode in environments:
        totals[mode] = {
            "characters": sum(row[mode] for row in rows),
            "estimated_tokens": sum(math.ceil(row[mode] / 4) for row in rows),
        }
    for label, size in retrieval.items():
        totals[f"delta_plus_{label}_read"] = {
            "characters": totals["delta"]["characters"] + size,
            "estimated_tokens": (
                totals["delta"]["estimated_tokens"] + math.ceil(size / 4)
            ),
        }
    repeats = {}
    for mode in environments:
        repeats[mode] = rows[1][mode] + rows[3][mode]
    return {
        "runs": rows,
        "totals": totals,
        "repeat_only_characters": repeats,
        "wrapper_executions": wrapper_executions,
        "pytest_executions": executions,
    }


def _versions(
    root: pathlib.Path, environment: dict[str, str]
) -> dict[str, str]:
    """Report executable versions, which can differ from package metadata."""
    versions = {"python": sys.version.split()[0]}
    for family in ("pytest", "ruff"):
        result = _run(
            [sys.executable, "-m", family, "--version"], root, environment
        )
        _require(
            result.returncode == 0, f"Install {family} in this interpreter"
        )
        versions[family] = result.stdout.strip().removeprefix(f"{family} ")
    return versions


def main() -> None:
    """Print measured fixture results after all preservation checks pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="token-saver-live-") as directory:
        root = pathlib.Path(directory)
        environments = {
            mode: _environment(root, mode) for mode in ("ordinary", "delta")
        }
        versions = _versions(root, environments["ordinary"])
        families = {
            family: _measure_family(family, root, environments)
            for family in ("pytest", "ruff")
        }
    report = {"versions": versions, "families": families}
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print("Real commands on disposable fixtures; five stages per mode.")
    print(
        "Versions: "
        + ", ".join(f"{key} {value}" for key, value in versions.items())
    )
    for family, results in families.items():
        print(f"\n{family}: stage              Ordinary chars  Delta chars")
        for row in results["runs"]:
            print(f"{row['stage']:26} {row['ordinary']:12} {row['delta']:12}")
        baseline = results["totals"]["ordinary"]["characters"]
        for label, totals in results["totals"].items():
            change = 100 * (1 - totals["characters"] / baseline)
            print(
                f"{label:26} {totals['characters']:6} chars "
                f"~{totals['estimated_tokens']:5} tokens; {change:+.1f}% saved"
            )
        repeats = results["repeat_only_characters"]
        reduction = 100 * (1 - repeats["delta"] / repeats["ordinary"])
        print(
            f"Repeat-only reduction: {reduction:.1f}% (excludes other stages)."
        )
    print("\nToken estimates sum ceil(characters / 4) for each response.")
    print("Includes retrieval output; excludes request/tool-call overhead.")
    print("Fixture results do not establish billing or agent-task savings.")


if __name__ == "__main__":
    main()
