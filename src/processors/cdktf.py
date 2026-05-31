"""CDKTF processor: cdktf deploy, diff, destroy, synth.

CDKTF wraps Terraform, so its plan/apply body is Terraform output.  We reuse
TerraformProcessor's plan/apply compression for that body and additionally
strip CDKTF's own synth/stack chrome.
"""

import re

from .base import Processor
from .terraform import TerraformProcessor

_CDKTF_CMD_RE = re.compile(r"\bcdktf\s+(deploy|diff|destroy|synth|plan)\b")
_CHROME_RE = re.compile(
    r"^(Generated Terraform code|Synthesizing|Running|Compiling|⏳|\[.*\]\s*(Synth|Compil))",
)


class CdktfProcessor(Processor):
    priority = 47
    hook_patterns = [
        r"^cdktf\s+(deploy|diff|destroy|synth|plan)\b",
    ]

    def __init__(self) -> None:
        self._tf = TerraformProcessor()

    @property
    def name(self) -> str:
        return "cdktf"

    def can_handle(self, command: str) -> bool:
        return bool(_CDKTF_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        # Strip CDKTF synth/compile chrome first.
        lines = [ln for ln in output.splitlines() if not _CHROME_RE.match(ln.strip())]
        if len(lines) <= 30:
            return output

        # Delegate the Terraform-style plan/apply body to the TF compressor.
        return self._tf._process_plan_apply(lines)
