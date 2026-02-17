"""Terraform output processor: plan, apply."""

import re

from .base import Processor


class TerraformProcessor(Processor):
    priority = 33
    hook_patterns = [
        r"^(terraform|tofu)\s+(plan|apply|destroy)\b",
    ]

    @property
    def name(self) -> str:
        return "terraform"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(terraform|tofu)\s+(plan|apply|destroy)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        result = []
        in_resource_block = False
        resource_action = ""

        for line in lines:
            stripped = line.strip()

            # Provider initialization — skip
            if re.match(r"^(Initializing|Acquiring|Installing|Reusing)\s+", stripped):
                continue
            if re.match(r"^-\s+Installed\s+", stripped):
                continue

            # Backend/state info — skip
            if re.match(r"^(Initializing the backend|Successfully configured)", stripped):
                continue

            # Resource change header: # resource.name will be created/destroyed/updated
            if re.match(r"^#\s+\S+", stripped) or re.match(r"^\s+#\s+\S+", stripped):
                in_resource_block = True
                resource_action = ""
                result.append(line)
                # Extract action
                if "will be created" in stripped:
                    resource_action = "+"
                elif "will be destroyed" in stripped:
                    resource_action = "-"
                elif "will be updated" in stripped or "must be replaced" in stripped:
                    resource_action = "~"
                continue

            # Resource block boundary
            if in_resource_block and re.match(r"^\s*[+~-]\s+resource\s+", stripped):
                result.append(line)
                continue
            if in_resource_block and stripped == "}":
                in_resource_block = False
                result.append(line)
                continue

            # Inside resource block — filter attributes
            if in_resource_block:
                # Changed attributes (lines with -> or ~ prefix)
                if "->" in stripped or re.match(r"^\s*[~+-]", stripped):
                    result.append(line)
                    continue

                # Known-after-apply — keep the key, it shows what will change
                if "(known after apply)" in stripped:
                    result.append(line)
                    continue

                # Forces replacement — important
                if "forces replacement" in stripped:
                    result.append(line)
                    continue

                # For create (+) actions, keep all attributes (they're new)
                if resource_action == "+":
                    result.append(line)
                    continue

                # For destroy (-), just the header is enough
                if resource_action == "-":
                    continue

                # For update (~), skip unchanged attributes
                continue

            # Plan/Apply summary lines — always keep
            if re.match(r"^Plan:", stripped):
                result.append(line)
                continue
            if re.match(r"^(Apply complete|Destroy complete|No changes)", stripped):
                result.append(line)
                continue

            # Changes to Outputs — keep
            if re.match(r"^Changes to Outputs:", stripped):
                result.append(line)
                continue

            # Output values
            if re.match(r"^\s*[+~-]\s+\w+\s*=", stripped):
                result.append(line)
                continue

            # Warnings and errors
            if re.search(r"\b(Error|Warning|error|warning)\b", stripped):
                result.append(line)
                continue

            # "Note:" lines
            if re.match(r"^Note:", stripped):
                result.append(line)
                continue

            # Blank lines between resources
            if not stripped and in_resource_block is False and result and result[-1].strip():
                result.append(line)

        return "\n".join(result) if result else output
