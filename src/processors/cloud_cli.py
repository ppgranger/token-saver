"""Cloud CLI output processor: aws, gcloud, az."""

import json
import re

from .base import Processor

_CLOUD_CMD_RE = re.compile(
    r"\b(aws|gcloud|az)\s+"
)

_IMPORTANT_KEY_RE = re.compile(
    r"(?i)(error|status|state|name|id|arn|message"
    r"|code|reason|type|tags?|key|value|label)"
)


class CloudCliProcessor(Processor):
    priority = 39
    hook_patterns = [
        r"^(aws|gcloud|az)\s+\S+",
    ]

    @property
    def name(self) -> str:
        return "cloud_cli"

    def can_handle(self, command: str) -> bool:
        return bool(_CLOUD_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        stripped = output.strip()

        # JSON output (most common for describe/list commands)
        if stripped.startswith(("{", "[")):
            return self._process_json(stripped, command)

        # Table output (aws with --output table, gcloud default)
        lines = output.splitlines()
        if len(lines) > 3 and self._is_table(lines):
            return self._process_table(lines)

        # Text/TSV output (aws --output text)
        if len(lines) > 30:
            return self._process_text(lines)

        return output

    def _process_json(self, output: str, command: str) -> str:
        """Compress deeply nested JSON from describe/list commands."""
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            lines = output.splitlines()
            if len(lines) <= 50:
                return output
            return self._truncate_text(lines)

        compressed = self._compress_json_value(data, depth=0, max_depth=4)
        result = json.dumps(compressed, indent=2, default=str)

        # Add summary if significant compression
        orig_lines = output.count("\n")
        new_lines = result.count("\n")
        if orig_lines > new_lines + 10:
            result += (
                f"\n\n({orig_lines + 1} lines compressed"
                f" to {new_lines + 1})"
            )

        return result

    def _compress_json_value(self, value, depth=0, max_depth=4):
        """Recursively compress JSON, truncating at depth."""
        if depth >= max_depth:
            if isinstance(value, dict):
                return f"{{... {len(value)} keys}}"
            if isinstance(value, list):
                return f"[... {len(value)} items]"
            if isinstance(value, str) and len(value) > 200:
                return value[:197] + "..."
            return value

        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                # Preserve important keys at full depth
                if _IMPORTANT_KEY_RE.match(k):
                    result[k] = self._compress_json_value(
                        v, depth, max_depth + 1
                    )
                else:
                    result[k] = self._compress_json_value(
                        v, depth + 1, max_depth
                    )
            return result

        if isinstance(value, list):
            if len(value) == 0:
                return value
            # Don't increment depth for list traversal
            if len(value) <= 5:
                return [
                    self._compress_json_value(item, depth, max_depth)
                    for item in value
                ]
            compressed = [
                self._compress_json_value(item, depth, max_depth)
                for item in value[:3]
            ]
            compressed.append(f"... ({len(value) - 3} more items)")
            return compressed

        if isinstance(value, str) and len(value) > 200:
            return value[:197] + "..."

        return value

    def _is_table(self, lines: list[str]) -> bool:
        """Detect table output format."""
        for line in lines[:5]:
            stripped = line.strip()
            if re.match(r"^[+\-|─┼]+$", stripped):
                return True
            if re.search(r"\w+\s{2,}\w+\s{2,}\w+", stripped):
                return True
        return False

    def _process_table(self, lines: list[str]) -> str:
        """Compress tabular output: keep header + limited rows."""
        header_end = 0
        for i, line in enumerate(lines[:5]):
            stripped = line.strip()
            if re.match(r"^[+\\-|─┼]+$", stripped):
                header_end = i + 1
            elif stripped and header_end > 0:
                break

        if header_end == 0:
            header_end = 1

        sep_re = re.compile(r"^[+\-|─┼]+$")
        data_lines = [
            row for row in lines[header_end:]
            if not sep_re.match(row.strip()) and row.strip()
        ]

        if len(data_lines) <= 20:
            return "\n".join(lines)

        result = lines[:header_end]
        result.extend(data_lines[:15])
        omitted = len(data_lines) - 20
        result.append(f"... ({omitted} more rows)")
        result.extend(data_lines[-5:])

        return "\n".join(result)

    def _process_text(self, lines: list[str]) -> str:
        """Compress text/TSV output."""
        if len(lines) <= 30:
            return "\n".join(lines)
        return self._truncate_text(lines)

    def _truncate_text(self, lines: list[str]) -> str:
        """Truncate long text output: keep first 20 + last 10."""
        if len(lines) <= 30:
            return "\n".join(lines)
        result = lines[:20]
        result.append(f"... ({len(lines) - 30} lines omitted)")
        result.extend(lines[-10:])
        return "\n".join(result)
