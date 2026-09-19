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

"""Observable contracts for portable compression and reproducible CI checks."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

import src.engine
import src.evaluation
import src.replay
from src import config

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    monkeypatch.setattr(config, "_config", dict(config._DEFAULTS))


class FakeCompressor:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def compress(self, command, output, *, exit_code=None):
        self.calls.append((command, output, exit_code))
        return self.output, "fake", output != self.output


def test_budget_violation_retains_full_output_and_exit_code():
    engine = FakeCompressor("ERROR: useful detail")
    result = src.evaluation.evaluate(
        engine,
        "deploy",
        "noise\nERROR: useful detail",
        exit_code=17,
        policy=src.evaluation.QualityPolicy(
            max_tokens=1, must_preserve=("ERROR: useful detail",)
        ),
    )
    assert result.compressed == "ERROR: useful detail"
    assert result.violations == ("max_tokens",)
    assert engine.calls[0][2] == 17


def test_required_text_checks_both_fixture_and_compressed_output():
    result = src.evaluation.evaluate(
        FakeCompressor("summary"),
        "test",
        "failure must remain",
        policy=src.evaluation.QualityPolicy(
            must_preserve=("failure", "fixture typo")
        ),
    )
    assert result.violations == (
        "must_preserve[0]:missing_in_output",
        "must_preserve[1]:missing_in_input",
    )


def test_reports_omit_raw_command_output_and_preservation_text():
    result = src.evaluation.evaluate(
        FakeCompressor("short"),
        "sensitive command",
        "private payload",
        policy=src.evaluation.QualityPolicy(must_preserve=("private payload",)),
    )
    serialized = json.dumps(result.report())
    for text in ("short", "sensitive command", "private payload"):
        assert text not in serialized


def test_token_estimates_round_up_and_limits_use_unrounded_savings():
    result = src.evaluation.evaluate(
        FakeCompressor("ab"),
        "x",
        "abc",
        policy=src.evaluation.QualityPolicy(min_savings_percent=33.334),
    )
    assert result.original_tokens == result.compressed_tokens == 1
    assert result.violations == ("min_savings_percent",)
    empty = src.evaluation.evaluate(
        FakeCompressor(""),
        "x",
        "",
        policy=src.evaluation.QualityPolicy(max_tokens=0),
    )
    assert empty.compressed_tokens == empty.original_tokens == 0
    assert not empty.violations


@pytest.mark.parametrize(
    "value", [0, -1, float("nan"), float("inf"), True, "4"]
)
def test_invalid_token_estimator_is_rejected(value):
    with pytest.raises(ValueError, match="chars_per_token"):
        src.evaluation.evaluate(
            FakeCompressor("x"), "x", "x", chars_per_token=value
        )


@pytest.mark.parametrize(
    "policy",
    [
        {"max_tokens": -1},
        {"max_tokens": True},
        {"max_tokens": 1.5},
        {"min_savings_percent": float("nan")},
        {"min_savings_percent": 101},
        {"min_savings_percent": True},
        {"must_preserve": ("",)},
    ],
)
def test_invalid_policy_cannot_silently_pass(policy):
    with pytest.raises(
        ValueError, match=r"max_tokens|min_savings_percent|must_preserve"
    ):
        src.evaluation.QualityPolicy(**policy)


def write_manifest(tmp_path, **changes):
    (tmp_path / "captured.txt").write_text(
        "noise\nERROR: required detail\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "cases": [
            {
                "name": "failure",
                "command": "never execute",
                "input": "captured.txt",
                "exit_code": 1,
                "must_preserve": ["ERROR: required detail"],
            }
        ],
        **changes,
    }
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_replay_aggregate_budget_fails_even_when_cases_pass(tmp_path):
    path = write_manifest(tmp_path, max_total_tokens=0)
    result = src.replay.replay(path, FakeCompressor("ERROR: required detail"))
    assert result["cases"][0]["passed"]
    assert not result["passed"]
    assert result["totals"]["violations"] == ["max_total_tokens"]


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"cases": []},
        {"max_total_tokens": -1},
        {"typo": True},
        {
            "cases": [
                {
                    "name": "x",
                    "command": "x",
                    "input": "captured.txt",
                    "max_token": 2,
                }
            ]
        },
        {
            "cases": [
                {
                    "name": "x",
                    "command": "x",
                    "input": "captured.txt",
                    "exit_code": True,
                }
            ]
        },
        {
            "cases": [
                {
                    "name": "x",
                    "command": "x",
                    "input": "captured.txt",
                    "must_preserve": "x",
                }
            ]
        },
    ],
)
def test_manifest_rejects_invalid_contracts(tmp_path, changes):
    with pytest.raises(
        ValueError,
        match=(
            r"schema_version|cases|max_tokens|supported|exit_code|must_preserve"
        ),
    ):
        src.replay.replay(
            write_manifest(tmp_path, **changes), FakeCompressor("x")
        )


def test_manifest_rejects_duplicate_names_before_compressing(tmp_path):
    case = {"name": "same", "command": "x", "input": "captured.txt"}
    engine = FakeCompressor("x")
    with pytest.raises(ValueError, match="unique"):
        src.replay.replay(write_manifest(tmp_path, cases=[case, case]), engine)
    assert not engine.calls


@pytest.mark.parametrize("escape", ["../outside.txt", "absolute", "symlink"])
def test_fixture_paths_cannot_escape_manifest_directory(tmp_path, escape):
    folder = tmp_path / "suite"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    if escape == "absolute":
        escape = str(outside)
    elif escape == "symlink":
        link = folder / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks unavailable for this user")
        escape = "link.txt"
    path = write_manifest(
        folder, cases=[{"name": "x", "command": "x", "input": escape}]
    )
    with pytest.raises(ValueError, match="inside the manifest directory"):
        src.replay.replay(path, FakeCompressor("x"))


def test_replay_rejects_oversized_and_invalid_utf8_captures(tmp_path):
    path = write_manifest(tmp_path)
    with pytest.raises(ValueError, match="max_output_bytes"):
        src.replay.replay(path, FakeCompressor("x"), max_input_bytes=1)
    (tmp_path / "captured.txt").write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        src.replay.replay(path, FakeCompressor("x"))


def run_cli(*args, input_text="", extra_env=None):
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "src.cli", *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_DIR,
        env={**os.environ, **(extra_env or {})},
        timeout=20,
        check=False,
    )


def test_compress_is_a_portable_filter_and_never_executes_label(tmp_path):
    marker = tmp_path / "must-not-exist"
    command = f'touch "{marker}"'
    result = run_cli(
        "compress", command, input_text="small output without newline"
    )
    assert result.returncode == 0
    assert result.stdout == "small output without newline"
    assert not marker.exists()


def test_cli_compress_redaction_survives_budget_failure():
    result = run_cli(
        "compress",
        "env",
        "--max-tokens",
        "0",
        "--format",
        "json",
        input_text="API_KEY=synthetic-private-secret\nPATH=/usr/bin\n",
    )
    assert result.returncode == 1
    assert "synthetic-private-secret" not in result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert "***" in report["output"]
    assert report["violations"] == ["max_tokens"]


def test_cli_failure_status_prevents_happy_path_routing():
    output = "unrecognized deployment diagnostic\n" * 10
    result = run_cli(
        "compress",
        "pip list",
        "--exit-code",
        "1",
        "--format",
        "json",
        input_text=output,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["processor"] == "generic"
    assert "unrecognized deployment diagnostic" in report["output"]


def test_compress_text_budget_failure_keeps_stdout_clean():
    result = run_cli(
        "compress", "unknown", "--max-tokens", "0", input_text="é useful error"
    )
    assert result.returncode == 1
    assert result.stdout == "é useful error"
    assert "exceeds budget" in result.stderr


def test_cli_replay_exit_codes_and_content_free_report(tmp_path):
    path = write_manifest(tmp_path)
    result = run_cli("replay", str(path), "--format", "json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["passed"]
    assert "required detail" not in result.stdout
    write_manifest(tmp_path, max_total_tokens=0)
    result = run_cli("replay", str(path))
    assert result.returncode == 1
    assert "FAIL max_total_tokens" in result.stdout
    path.write_text("invalid JSON", encoding="utf-8")
    result = run_cli("replay", str(path))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_cli_rejects_oversized_stdin():
    result = run_cli(
        "compress",
        "x",
        input_text="abcdef",
        extra_env={"TOKEN_SAVER_MAX_OUTPUT_BYTES": "2"},
    )
    assert result.returncode == 2
    assert not result.stdout


@pytest.mark.parametrize(
    "malformed", ["deep", "huge_limit", "directory", "loop"]
)
def test_malformed_manifests_have_input_error_status(tmp_path, malformed):
    path = write_manifest(tmp_path)
    if malformed == "deep":
        path.write_text("[" * 2000 + "]" * 2000, encoding="utf-8")
    elif malformed == "huge_limit":
        path = write_manifest(
            tmp_path,
            cases=[
                {
                    "name": "x",
                    "command": "x",
                    "input": "captured.txt",
                    "min_savings_percent": 10**1000,
                }
            ],
        )
    elif malformed == "directory":
        path = tmp_path
    else:
        link = tmp_path / "loop"
        try:
            link.symlink_to(link)
        except OSError:
            pytest.skip("symlinks unavailable for this user")
        path = write_manifest(
            tmp_path,
            cases=[
                {
                    "name": "x",
                    "command": "x",
                    "input": "loop",
                }
            ],
        )
    result = run_cli("replay", str(path))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_real_replay_example_passes():
    report = src.replay.replay(
        REPO_DIR / "examples" / "quality-replay.json",
        src.engine.CompressionEngine(),
    )
    assert report["passed"], report
