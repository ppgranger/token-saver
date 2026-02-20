"""Terraform output processor: plan, apply, init, output, state."""

import re

from .base import Processor

_TF_CMD_RE = re.compile(
    r"\b(terraform|tofu)\s+(plan|apply|destroy|init|output|state\s+(?:list|show))\b"
)


class TerraformProcessor(Processor):
    priority = 33
    hook_patterns = [
        r"^(terraform|tofu)\s+(plan|apply|destroy|init|output|state\s+(list|show))\b",
    ]

    @property
    def name(self) -> str:
        return "terraform"

    def can_handle(self, command: str) -> bool:
        return bool(_TF_CMD_RE.search(command))

    def _get_subcmd(self, command: str) -> str | None:
        """Extract the terraform subcommand."""
        m = _TF_CMD_RE.search(command)
        return m.group(2) if m else None

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        subcmd = self._get_subcmd(command)
        if subcmd == "init":
            return self._process_init(output)
        if subcmd == "output":
            return self._process_output(output)
        if subcmd and subcmd.startswith("state"):
            return self._process_state(output)

        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        return self._process_plan_apply(lines)

    def _process_plan_apply(self, lines: list[str]) -> str:
        """Compress terraform plan/apply/destroy output."""
        result = []
        in_resource_block = False
        resource_action = ""

        for line in lines:
            stripped = line.strip()

            # Provider initialization -- skip
            if re.match(r"^(Initializing|Acquiring|Installing|Reusing)\s+", stripped):
                continue
            if re.match(r"^-\s+Installed\s+", stripped):
                continue

            # Backend/state info -- skip
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

            # Inside resource block -- filter attributes
            if in_resource_block:
                # Changed attributes (lines with -> or ~ prefix)
                if "->" in stripped or re.match(r"^\s*[~+-]", stripped):
                    result.append(line)
                    continue

                # Known-after-apply -- keep the key, it shows what will change
                if "(known after apply)" in stripped:
                    result.append(line)
                    continue

                # Forces replacement -- important
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

            # Plan/Apply summary lines -- always keep
            if re.match(r"^Plan:", stripped):
                result.append(line)
                continue
            if re.match(r"^(Apply complete|Destroy complete|No changes)", stripped):
                result.append(line)
                continue

            # Changes to Outputs -- keep
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

        return "\n".join(result) if result else "\n".join(lines)

    def _process_init(self, output: str) -> str:
        """Compress terraform init: keep providers, warnings, errors, success."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        for line in lines:
            stripped = line.strip()

            # Keep provider version info: "- Installed hashicorp/aws v5.31.0 ..."
            if re.search(r"\bv\d+\.\d+", stripped) and re.match(r"^-\s+", stripped):
                result.append(stripped)
                continue

            # Keep final result
            if re.search(r"(successfully initialized|has been successfully|Terraform has been)", stripped, re.I):
                result.append(stripped)
                continue

            # Keep errors/warnings
            if re.search(r"\b(Error|Warning|error|warning)\b", stripped):
                result.append(stripped)
                continue

            # Keep upgrade/reinitialization notices
            if re.search(r"(upgrade available|new version|rerun with -upgrade)", stripped, re.I):
                result.append(stripped)
                continue

            # Skip verbose initialization messages
            if re.match(r"^(Initializing|Acquiring|Installing|Reusing|Finding|Using)\s+", stripped):
                continue

        if not result:
            return output
        return "\n".join(result)

    def _process_output(self, output: str) -> str:
        """Compress terraform output: truncate long values."""
        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        result = []
        for line in lines:
            # Truncate very long output values
            if len(line) > 200:
                key_match = re.match(r"^(\S+\s*=\s*)", line)
                if key_match:
                    result.append(f"{key_match.group(1)}... ({len(line)} chars)")
                else:
                    result.append(line[:150] + f"... ({len(line)} chars)")
            else:
                result.append(line)

        return "\n".join(result)

    def _process_state(self, output: str) -> str:
        """Compress terraform state list/show."""
        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        # state list: just resource names
        if all(re.match(r"^\S", line) for line in lines if line.strip()):
            result = [f"{len(lines)} resources in state:"]
            # Group by resource type
            by_type: dict[str, int] = {}
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Extract type: module.x.aws_instance.y -> aws_instance
                parts = stripped.split(".")
                for part in parts:
                    if re.match(r"^[a-z]+_", part):
                        by_type[part] = by_type.get(part, 0) + 1
                        break
                else:
                    by_type[stripped] = by_type.get(stripped, 0) + 1

            for rtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
                result.append(f"  {rtype}: {count}")
            return "\n".join(result)

        # state show: truncate long attribute values
        result = []
        for line in lines:
            if len(line) > 200:
                key_match = re.match(r"^(\s*\S+\s*=\s*)", line)
                if key_match:
                    result.append(f"{key_match.group(1)}... ({len(line)} chars)")
                else:
                    result.append(line[:150] + f"... ({len(line)} chars)")
            else:
                result.append(line)

        if len(result) > 80:
            return "\n".join(result[:60]) + f"\n... ({len(result) - 60} more lines)"
        return "\n".join(result)
