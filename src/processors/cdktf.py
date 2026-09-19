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

"""CDKTF processor: cdktf deploy, diff, destroy, synth.

CDKTF wraps Terraform, so its plan/apply body is Terraform output.  We reuse
TerraformProcessor's plan/apply compression for that body and additionally
strip CDKTF's own synth/stack chrome.
"""

import re

from src.processors import base
from src.processors import terraform

_CDKTF_CMD_RE = re.compile(r"\bcdktf\s+(deploy|diff|destroy|synth|plan)\b")
_CHROME_RE = re.compile(
    (
        r"^(Generated Terraform code|Synthesizing|Running|Compiling|⏳|"
        r"\[.*\]\s*(Synth|Compil))"
    ),
)


class CdktfProcessor(base.Processor):
    """Remove CDKTF progress before summarizing Terraform resource changes."""

    priority = 47
    handles_failure = True
    hook_patterns = [
        r"^cdktf\s+(deploy|diff|destroy|synth|plan)\b",
    ]

    def __init__(self) -> None:
        """Create the Terraform delegate for CDKTF resource output."""
        self._tf = terraform.TerraformProcessor()

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "cdktf"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(_CDKTF_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        """Compress captured output according to this processor's rules.

        Args:
            command: Original shell command used to select output handling.
            output: Captured command output before this transformation.

        Returns:
            Compressed text, or the input when no safe reduction is available.
        """
        if not output or not output.strip():
            return output

        # Strip CDKTF synth/compile chrome first.
        lines = [
            ln for ln in output.splitlines() if not _CHROME_RE.match(ln.strip())
        ]
        if len(lines) <= 30:
            return output

        # Delegate the Terraform-style plan/apply body to the TF compressor.
        return self._tf.process_plan_apply(lines)
