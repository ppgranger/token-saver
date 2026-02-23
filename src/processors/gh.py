"""GitHub CLI output processor: gh pr, gh issue, gh run, gh repo."""

import json
import re

from .. import config
from .base import Processor
from .utils import compress_diff

_GH_CMD_RE = re.compile(
    r"\bgh\s+(?:(pr|issue|run|repo|release|workflow)\s+"
    r"(list|view|status|diff|checks|ls|create|close|merge)"
    r"|api\s+\S+)\b"
)

_VIEW_META_RE = re.compile(
    r"^(title|state|author|number|url|labels|reviewers|assignees"
    r"|milestone|projects|base|head|created|updated|closed|merged):",
    re.I,
)

_STATUS_INDICATOR_RE = re.compile(
    r"(FAIL|OPEN|CLOSED|MERGED|APPROVED|CHANGES_REQUESTED"
    r"|REVIEW_REQUIRED|\u2713|\u2717|\xd7|!)"
)

_PENDING_RE = re.compile(r"\bpending\b|\bqueued\b|\bin_progress\b", re.I)


class GhProcessor(Processor):
    priority = 37
    hook_patterns = [
        r"^gh\s+(pr|issue|run|repo|release|workflow)\s+(list|view|status|diff|checks|ls)\b",
        r"^gh\s+api\s+\S+",
    ]

    @property
    def name(self) -> str:
        return "gh"

    def can_handle(self, command: str) -> bool:
        return bool(_GH_CMD_RE.search(command))

    def _get_subcmd(self, command: str) -> tuple[str, str] | None:
        # Detect gh api first
        if re.search(r"\bgh\s+api\s+", command):
            return ("api", "api")
        m = _GH_CMD_RE.search(command)
        if m and m.group(1):
            return (m.group(1), m.group(2))
        return None

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        subcmd = self._get_subcmd(command)
        if not subcmd:
            return output

        resource, action = subcmd

        if resource == "api":
            return self._process_api(output)
        if action == "list":
            return self._process_list(output, resource)
        if action == "view":
            return self._process_view(output, resource)
        if action == "status":
            return self._process_status(output, resource)
        if action == "diff":
            return self._process_diff(output)
        if action == "checks":
            return self._process_checks(output)
        return output

    def _process_list(self, output: str, resource: str) -> str:
        """Compress gh list output: tabular format with wide columns."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        result = []
        for line in lines[:30]:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split("\t")
            compressed_parts = []
            for p in parts:
                p = p.strip()  # noqa: PLW2901
                if len(p) > 80:
                    p = p[:77] + "..."  # noqa: PLW2901
                compressed_parts.append(p)
            result.append("\t".join(compressed_parts))

        if len(lines) > 30:
            result.append(f"... ({len(lines) - 30} more {resource}s)")

        return "\n".join(result)

    def _process_view(self, output: str, resource: str) -> str:
        """Compress gh view output: keep key fields, compress body."""
        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        result = []
        in_body = False
        body_lines = []

        for line in lines:
            stripped = line.strip()

            if _VIEW_META_RE.match(stripped):
                result.append(line)
                continue

            if stripped.startswith("--") and stripped.endswith("--"):
                if body_lines:
                    result.extend(self._compress_body(body_lines))
                    body_lines = []
                in_body = True
                result.append(line)
                continue

            if in_body:
                body_lines.append(line)
            else:
                result.append(line)

        if body_lines:
            result.extend(self._compress_body(body_lines))

        return "\n".join(result)

    def _compress_body(self, lines: list[str]) -> list[str]:
        """Compress PR/issue body: keep first 20 lines, truncate rest."""
        if len(lines) <= 20:
            return lines
        return [*lines[:20], f"... ({len(lines) - 20} more body lines)"]

    def _process_status(self, output: str, resource: str) -> str:
        """Compress gh status: keep failing/action-needed items."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith(" ") and stripped:
                result.append(line)
                continue
            if _STATUS_INDICATOR_RE.search(stripped):
                result.append(line)
                continue
            if len(lines) > 30:
                continue
            result.append(line)

        return "\n".join(result) if result else output

    def _process_diff(self, output: str) -> str:
        """Compress gh pr diff: delegates to shared diff utility."""
        lines = output.splitlines()
        if len(lines) <= 50:
            return output

        max_hunk = config.get("max_diff_hunk_lines")
        max_context = config.get("max_diff_context_lines")
        result = compress_diff(lines, max_hunk, max_context)
        return "\n".join(result)

    def _process_api(self, output: str) -> str:
        """Compress gh api output: JSON compression."""
        stripped = output.strip()
        if not stripped.startswith(("{", "[")):
            return output

        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return output

        if len(stripped) < 500:
            return output

        compressed = self._summarize_json(data, depth=0, max_depth=3)
        orig_lines = stripped.count("\n") + 1
        new_lines = compressed.count("\n") + 1
        result = compressed
        if orig_lines > new_lines + 10:
            result += f"\n\n({orig_lines} lines compressed to {new_lines})"
        return result

    def _summarize_json(self, val, depth: int, max_depth: int) -> str:
        """Recursively summarize a JSON value."""
        indent = "  " * depth
        if isinstance(val, dict):
            if depth >= max_depth:
                return f"{{{len(val)} keys}}"
            items = []
            for k, v in val.items():
                summarized = self._summarize_json(v, depth + 1, max_depth)
                items.append(f'{indent}  "{k}": {summarized}')
            return "{\n" + ",\n".join(items) + f"\n{indent}}}"
        elif isinstance(val, list):
            if len(val) == 0:
                return "[]"
            if len(val) <= 3:
                inner = [self._summarize_json(v, depth + 1, max_depth) for v in val]
                return "[" + ", ".join(inner) + "]"
            first = self._summarize_json(val[0], depth + 1, max_depth)
            return f"[{first}, ... ({len(val)} items total)]"
        elif isinstance(val, str):
            if len(val) > 80:
                return f'"{val[:60]}..." ({len(val)} chars)'
            return json.dumps(val)
        else:
            return json.dumps(val)

    def _process_checks(self, output: str) -> str:
        """Compress gh pr checks: collapse passing checks."""
        lines = output.splitlines()
        if len(lines) <= 10:
            return output

        passed = 0
        failed = []
        pending = []
        other = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.search(r"\bpass\b", stripped, re.I) or "\u2713" in stripped:
                passed += 1
            elif (
                re.search(r"\bfail\b", stripped, re.I) or "\u2717" in stripped or "\xd7" in stripped
            ):
                failed.append(stripped)
            elif _PENDING_RE.search(stripped) or "\u25cb" in stripped:
                pending.append(stripped)
            else:
                other.append(stripped)

        result = []
        if failed:
            result.append(f"Failed ({len(failed)}):")
            result.extend(f"  {f}" for f in failed)
        if pending:
            result.append(f"Pending ({len(pending)}):")
            result.extend(f"  {p}" for p in pending)
        if passed > 0:
            result.append(f"[{passed} checks passed]")
        if other:
            result.extend(other[:5])

        return "\n".join(result) if result else output
