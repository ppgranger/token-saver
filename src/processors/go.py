"""Go processor: go build, vet, mod, generate, install."""

import re
from collections import defaultdict

from .. import config
from .base import Processor

_GO_CMD_RE = re.compile(r"\bgo\s+(build|vet|mod|generate|install)\b")
_GO_ERROR_RE = re.compile(r"^(\S+\.go):(\d+):(\d+):\s+(.+)$")
_GO_PACKAGE_RE = re.compile(r"^#\s+(\S+)")
_GO_DOWNLOADING_RE = re.compile(r"^go:\s+downloading\s+(\S+)\s+v")
_GO_MOD_ACTION_RE = re.compile(r"^go:\s+(added|upgraded|downgraded|removed)\s+")
_GO_GENERATE_RUN_RE = re.compile(r"^(\S+\.go):\d+:\s+running\s+")


class GoProcessor(Processor):
    priority = 23
    hook_patterns = [
        r"^go\s+(build|vet|mod|generate|install)\b",
    ]

    @property
    def name(self) -> str:
        return "go"

    def can_handle(self, command: str) -> bool:
        if re.search(r"\bgo\s+test\b", command):
            return False
        if re.search(r"\bgolangci-lint\b", command):
            return False
        return bool(_GO_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        m = _GO_CMD_RE.search(command)
        if not m:
            return output

        subcmd = m.group(1)
        if subcmd == "build":
            return self._process_go_build(output)
        if subcmd == "install":
            return self._process_go_build(output)
        if subcmd == "vet":
            return self._process_go_vet(output)
        if subcmd == "mod":
            return self._process_go_mod(output)
        if subcmd == "generate":
            return self._process_go_generate(output)
        return output

    def _process_go_build(self, output: str) -> str:
        lines = output.splitlines()
        result: list[str] = []
        package_lines: list[str] = []
        error_lines: list[str] = []
        has_errors = False

        for line in lines:
            stripped = line.strip()

            if _GO_ERROR_RE.match(stripped):
                has_errors = True
                error_lines.append(line)
            elif _GO_PACKAGE_RE.match(stripped):
                package_lines.append(line)
            elif stripped and has_errors:
                # Context lines after an error (e.g., code snippet, notes)
                error_lines.append(line)

        if not has_errors:
            # No errors but output exists — could be warnings or linker errors
            return output

        # For multi-package builds, keep package headers
        if len(package_lines) > 1:
            result.extend(package_lines[:3])
            if len(package_lines) > 3:
                result.append(f"... ({len(package_lines) - 3} more packages)")

        result.extend(error_lines)
        return "\n".join(result) if result else output

    def _categorize_vet_warning(self, msg: str) -> str:
        msg_lower = msg.lower()
        if "printf" in msg_lower:
            return "printf"
        if "unreachable" in msg_lower:
            return "unreachable"
        if "shadow" in msg_lower:
            return "shadow"
        if "unused" in msg_lower:
            return "unused"
        if "nil" in msg_lower:
            return "nil"
        if "loop" in msg_lower:
            return "loop"
        return "other"

    def _process_go_vet(self, output: str) -> str:
        lines = output.splitlines()
        warnings_by_type: dict[str, list[str]] = defaultdict(list)
        package_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            m = _GO_ERROR_RE.match(stripped)
            if m:
                msg = m.group(4)
                wtype = self._categorize_vet_warning(msg)
                warnings_by_type[wtype].append(line)
            elif _GO_PACKAGE_RE.match(stripped):
                package_lines.append(line)

        if not warnings_by_type:
            return output

        example_count = config.get("lint_example_count")
        group_threshold = config.get("lint_group_threshold")
        result: list[str] = []

        if package_lines:
            result.extend(package_lines[:2])

        for wtype, warnings in sorted(warnings_by_type.items(), key=lambda x: -len(x[1])):
            count = len(warnings)
            if count >= group_threshold:
                result.append(f"{wtype}: {count} warnings")
                for w in warnings[:example_count]:
                    result.append(f"  {w}")
                if count > example_count:
                    result.append(f"  ... ({count - example_count} more)")
            else:
                result.extend(warnings)

        return "\n".join(result) if result else output

    def _process_go_mod(self, output: str) -> str:
        lines = output.splitlines()
        download_count = 0
        action_lines: list[str] = []
        other_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if _GO_DOWNLOADING_RE.match(stripped):
                download_count += 1
            elif _GO_MOD_ACTION_RE.match(stripped):
                action_lines.append(line)
            elif stripped:
                other_lines.append(line)

        result: list[str] = []
        if download_count > 0:
            result.append(f"[{download_count} packages downloaded]")
        result.extend(action_lines)
        result.extend(other_lines)

        return "\n".join(result) if result else output

    def _process_go_generate(self, output: str) -> str:
        lines = output.splitlines()
        generate_count = 0
        result: list[str] = []

        for line in lines:
            stripped = line.strip()
            if _GO_GENERATE_RUN_RE.match(stripped):
                generate_count += 1
            elif stripped:
                result.append(line)

        if generate_count > 0:
            result.insert(0, f"[{generate_count} generators ran]")

        return "\n".join(result) if result else output
