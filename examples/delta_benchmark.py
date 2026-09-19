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

"""Measure five synthetic pytest captures and optional detail retrieval.

Run ``python3 examples/delta_benchmark.py`` without external packages or
subprocesses. Configuration, audit logs and snapshots use a disposable profile.
"""

import argparse
import contextlib
import io
import logging
import math
import os
import pathlib
import re
import sys
import tempfile


def _failure(name: str, actual: int, line: int) -> str:
    """Build a synthetic pytest verbose list-diff failure with stable lines."""
    lines = [
        f"________________ {name} ________________",
        "",
        f"    def {name}():",
        "        observed = list(range(30))",
        f"        observed[-1] = {actual}",
        ">       assert observed == list(range(30))",
        f"E       assert [0, 1, ..., {actual}] == [0, 1, ..., 29]",
        f"E         At index 29 diff: {actual} != 29",
        "E         Full diff:",
        "E           [",
    ]
    lines.extend(f"E               {number}," for number in range(29))
    lines.extend(
        [
            "E         -     29,",
            f"E         +     {actual},",
            "E           ]",
            "",
            f"tests/test_service.py:{line}: AssertionError",
            "",
        ]
    )
    return "\n".join(lines)


def _capture(edited: bool) -> str:
    """Build a complete run with a fix, changed failure and new regression."""
    failures = {
        "test_payload": (-1, 18),
        "test_status": (-2 if edited else -1, 29),
        "test_invoice" if edited else "test_cache": (-1, 40),
    }
    lines = [
        "================ test session starts ================",
        "platform linux -- Python 3.12.0, pytest-8.0.0",
        "rootdir: /synthetic/project",
        "collected 34 items",
        "",
    ]
    for index in range(30):
        lines.append(f"tests/test_service.py::test_success[{index}] PASSED")
    for name in ("test_payload", "test_status", "test_cache", "test_invoice"):
        status = "FAILED" if name in failures else "PASSED"
        lines.append(f"tests/test_service.py::{name} {status}")
    lines.extend(["", "================ FAILURES ================"])
    for name, (actual, line) in failures.items():
        lines.append(_failure(name, actual, line))
    lines.append("========= short test summary info =========")
    for name, (actual, _) in failures.items():
        lines.append(
            f"FAILED tests/test_service.py::{name} - "
            f"assert [0, 1, ..., {actual}] == [0, 1, ..., 29]"
        )
    lines.append("============= 3 failed, 31 passed in 0.12s =============")
    return "\n".join(lines) + "\n"


def _measure() -> None:
    """Measure output sizes through the engine and detail-retrieval CLI."""
    # Import runtime modules only after main isolates their profile and cwd.
    # pylint: disable=import-outside-toplevel
    from src import config  # noqa: PLC0415
    from src import core  # noqa: PLC0415
    from src import delta  # noqa: PLC0415
    from src import delta_cli  # noqa: PLC0415
    from src import engine  # noqa: PLC0415

    config.reload()
    compressor = engine.CompressionEngine()
    ordinary_total = ordinary_tokens = 0
    delta_total = delta_tokens = 0
    ratio = config.get("chars_per_token")
    print("Synthetic pytest sequence: baseline, repeat, edit, repeat, repeat")
    print("Run   Ordinary chars   Delta chars")
    last_output = ""
    for number, edited in enumerate((False, False, True, True, True), start=1):
        output = _capture(edited)
        ordinary = core.compress(
            "pytest -vv", output, engine=compressor, exit_code=1
        )
        result = delta.apply(
            "pytest -vv",
            output,
            ordinary,
            engine=compressor,
            exit_code=1,
            session_id="synthetic-benchmark",
        )
        ordinary_total += len(ordinary.compressed)
        delta_total += len(result.compressed)
        ordinary_tokens += math.ceil(len(ordinary.compressed) / ratio)
        delta_tokens += math.ceil(len(result.compressed) / ratio)
        last_output = result.compressed
        print(
            f"{number:3}   {len(ordinary.compressed):14}   "
            f"{len(result.compressed):11}"
        )
    reference = re.search(r"delta show ([0-9a-f]{32})", last_output)
    if reference is None:
        raise RuntimeError(
            "Scenario did not produce a retrievable Delta result"
        )
    totals = {
        "Ordinary compression": (ordinary_total, ordinary_tokens),
        "Delta": (delta_total, delta_tokens),
    }
    for label, diagnostic in (
        ("Delta + one diagnostic read", "tests/test_service.py::test_payload"),
        ("Delta + one complete read", None),
    ):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            delta_cli.cmd_show(
                argparse.Namespace(run_id=reference[1], diagnostic=diagnostic)
            )
        count = len(captured.getvalue())
        totals[label] = (
            delta_total + count,
            delta_tokens + math.ceil(count / ratio),
        )
    print(f"\nTotals; tokens sum ceil(characters / {ratio}) per response:")
    for label, (count, tokens) in totals.items():
        difference = 100 * (1 - count / ordinary_total)
        print(
            f"{label:29} {count:6} chars  ~{tokens:5} tokens"
            f"  {difference:6.1f}% less than ordinary"
        )
    print("Synthetic output only; no agent task or billing savings measured.")


def main() -> None:
    """Run with a disposable profile, restoring the caller's environment."""
    repository = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repository))
    original_environment = os.environ.copy()
    original_directory = pathlib.Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix="token-saver-delta-") as temp:
            for key in tuple(os.environ):
                if key.startswith("TOKEN_SAVER_"):
                    del os.environ[key]
            os.environ.update(
                {"HOME": temp, "USERPROFILE": temp, "APPDATA": temp}
            )
            os.environ["TOKEN_SAVER_DB_DIR"] = temp
            # These names describe feature switches, not credential values.
            os.environ.update(
                TOKEN_SAVER_ENABLED="true",  # noqa: S106
                TOKEN_SAVER_DELTA_ENABLED="true",  # noqa: S106
            )
            os.chdir(temp)
            try:
                _measure()
            finally:
                # Release the temporary audit log before Windows removes it.
                logging.shutdown()
                os.chdir(original_directory)
    finally:
        os.chdir(original_directory)
        os.environ.clear()
        os.environ.update(original_environment)


if __name__ == "__main__":
    main()
