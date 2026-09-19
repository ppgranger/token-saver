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

"""Regressions for CDKTF's delegation of captured Terraform lines."""

import pytest

from src.processors import cdktf
from src.processors import terraform

_PLAN_SUMMARY = "Plan: 1 to add, 0 to change, 0 to destroy."


@pytest.mark.parametrize(
    ("initializations", "blank_lines"),
    [(29, 1), (30, 0), (35, 1), (35, 2)],
)
def test_cdktf_keeps_threshold_and_trailing_blank_line_semantics(
    initializations, blank_lines
):
    lines = [
        f"Initializing provider {index}" for index in range(initializations)
    ]
    lines.append(_PLAN_SUMMARY)
    lines.extend([""] * blank_lines)
    output = "\n".join(lines) + "\n"

    result = cdktf.CdktfProcessor().process("cdktf diff", output)

    assert result == _PLAN_SUMMARY + ("\n" if blank_lines else "")


def test_cdktf_checks_its_threshold_after_removing_progress():
    lines = ["Generated Terraform code"] * 100
    lines.extend(f"Initializing provider {index}" for index in range(29))
    lines.append(_PLAN_SUMMARY)
    output = "\n".join(lines) + "\n"

    assert cdktf.CdktfProcessor().process("cdktf deploy", output) == output


def test_public_plan_delegate_accepts_selected_lines_without_a_size_gate():
    lines = ["Initializing provider", _PLAN_SUMMARY, ""]
    original = list(lines)

    result = terraform.TerraformProcessor().process_plan_apply(lines)

    assert result == _PLAN_SUMMARY + "\n"
    assert lines == original
