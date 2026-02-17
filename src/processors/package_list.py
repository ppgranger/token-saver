"""Package listing processor: pip list/freeze, npm ls/list, conda list."""

import re

from .base import Processor


class PackageListProcessor(Processor):
    priority = 15
    hook_patterns = [
        r"^(pip3?\s+(list|freeze)|npm\s+(ls|list)|conda\s+list|gem\s+list|brew\s+list)\b",
    ]

    @property
    def name(self) -> str:
        return "package_list"

    def can_handle(self, command: str) -> bool:
        return bool(
            re.search(
                r"\b(pip3?\s+(list|freeze)|npm\s+(ls|list)|conda\s+list|"
                r"yarn\s+list|pnpm\s+list|gem\s+list|brew\s+list)\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if re.search(r"\bnpm\s+(ls|list)\b", command):
            return self._process_npm_ls(output)
        if re.search(r"\bpip3?\s+freeze\b", command):
            return self._process_pip_freeze(output)
        if re.search(r"\bpip3?\s+list\b", command):
            return self._process_pip_list(output)
        if re.search(r"\bconda\s+list\b", command):
            return self._process_conda_list(output)
        if re.search(r"\b(yarn|pnpm)\s+list\b", command):
            return self._process_npm_ls(output)
        if re.search(r"\bgem\s+list\b", command):
            return self._process_gem_list(output)
        if re.search(r"\bbrew\s+list\b", command):
            return self._process_simple_list(output, "formulae")
        return output

    def _process_pip_list(self, output: str) -> str:
        """Compress pip list: show count + first entries."""
        lines = output.splitlines()

        # Skip header lines (Package/Version separator)
        data_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^-+\s+-+", stripped):
                continue
            if re.match(r"^Package\s+Version", stripped):
                continue
            if stripped:
                data_lines.append(stripped)

        if len(data_lines) <= 20:
            return output

        result = [f"{len(data_lines)} packages installed:"]
        for line in data_lines[:15]:
            result.append(f"  {line}")
        result.append(f"  ... ({len(data_lines) - 15} more)")
        return "\n".join(result)

    def _process_pip_freeze(self, output: str) -> str:
        """Compress pip freeze: show count + first entries."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]

        if len(lines) <= 20:
            return output

        result = [f"{len(lines)} packages:"]
        for line in lines[:15]:
            result.append(f"  {line}")
        result.append(f"  ... ({len(lines) - 15} more)")
        return "\n".join(result)

    def _process_npm_ls(self, output: str) -> str:
        """Compress npm ls: collapse dependency tree, keep top-level + issues."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        top_level = []
        issues = []
        total_deps = 0

        for line in lines:
            stripped = line.strip()

            # Unmet/invalid dependencies — always keep
            if re.search(r"(UNMET|invalid|missing|ERR!|WARN)", stripped, re.I):
                issues.append(stripped)
                continue

            # Top-level: lines with only one level of tree indent (├── or └──)
            if re.match(r"^[├└]──\s+", line) or re.match(r"^[+`]-\s+", line):
                top_level.append(stripped)
                total_deps += 1
                continue

            # Deeper dependencies
            if re.match(r"^[│ ]*[├└]", line) or re.match(r"^[| ]*[+`]", line):
                total_deps += 1
                continue

            # Root line or summary
            if line and not line.startswith(" "):
                top_level.insert(0, stripped)

        result = [f"{total_deps} total dependencies:"]
        if issues:
            result.append(f"Issues ({len(issues)}):")
            for issue in issues[:10]:
                result.append(f"  {issue}")
            if len(issues) > 10:
                result.append(f"  ... ({len(issues) - 10} more)")
        result.append(f"Top-level ({len(top_level)}):")
        for pkg in top_level[:20]:
            result.append(f"  {pkg}")
        if len(top_level) > 20:
            result.append(f"  ... ({len(top_level) - 20} more)")

        return "\n".join(result)

    def _process_conda_list(self, output: str) -> str:
        """Compress conda list output."""
        lines = output.splitlines()
        data_lines = [line for line in lines if line.strip() and not line.startswith("#")]

        if len(data_lines) <= 20:
            return output

        result = [f"{len(data_lines)} packages installed:"]
        for line in data_lines[:15]:
            result.append(f"  {line.strip()}")
        result.append(f"  ... ({len(data_lines) - 15} more)")
        return "\n".join(result)

    def _process_gem_list(self, output: str) -> str:
        """Compress gem list output."""
        return self._process_simple_list(output, "gems")

    def _process_simple_list(self, output: str, item_type: str) -> str:
        """Generic list compressor for simple one-item-per-line lists."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) <= 20:
            return output

        result = [f"{len(lines)} {item_type}:"]
        for line in lines[:15]:
            result.append(f"  {line}")
        result.append(f"  ... ({len(lines) - 15} more)")
        return "\n".join(result)
