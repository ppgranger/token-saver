"""JQ/YQ processor: compress large JSON and YAML outputs."""

import json
import re

from .. import config
from .base import Processor
from .utils import compress_json_value

_JQ_RE = re.compile(r"\bjq\b")
_YQ_RE = re.compile(r"\byq\b")


class JqYqProcessor(Processor):
    priority = 44
    hook_patterns = [
        r"^(jq|yq)\b",
    ]

    @property
    def name(self) -> str:
        return "jq_yq"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(jq|yq)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        threshold = config.get("jq_passthrough_threshold")
        if len(lines) <= threshold:
            return output

        if _JQ_RE.search(command):
            return self._process_jq(output, lines)
        return self._process_yq(output, lines)

    def _process_jq(self, output: str, lines: list[str]) -> str:
        # Try parsing as a single JSON document
        try:
            data = json.loads(output.strip())
            compressed = compress_json_value(data, max_depth=4)
            result = json.dumps(compressed, indent=2)
            if len(result) < len(output):
                return result + f"\n({len(lines)} lines compressed)"
            return output
        except (json.JSONDecodeError, ValueError):
            pass

        # Streaming mode: one JSON value per line
        return self._process_streaming_json(lines)

    @staticmethod
    def _parse_json_keys(line: str) -> str | None:
        try:
            obj = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(obj, dict):
            return ",".join(sorted(obj.keys()))
        return None

    def _process_streaming_json(self, lines: list[str]) -> str:
        structures: list[str] = []
        for line in lines[:5]:
            keys = self._parse_json_keys(line)
            if keys is None:
                break
            structures.append(keys)

        # If all parsed lines have the same keys, it's a repeated structure
        if len(structures) >= 3 and len(set(structures)) == 1:
            result = list(lines[:3])
            result.append(f"... ({len(lines) - 3} more items with same structure)")
            return "\n".join(result)

        keep_head = 20
        keep_tail = 10
        if len(lines) <= keep_head + keep_tail:
            return "\n".join(lines)

        result = lines[:keep_head]
        result.append(f"\n... ({len(lines) - keep_head - keep_tail} lines truncated) ...\n")
        result.extend(lines[-keep_tail:])
        return "\n".join(result)

    def _process_yq(self, output: str, lines: list[str]) -> str:
        # Count top-level keys and list items
        top_level_keys = 0
        list_items = 0
        for line in lines:
            if line and not line[0].isspace() and line.rstrip().endswith(":"):
                top_level_keys += 1
            elif re.match(r"^- ", line) or re.match(r"^  - ", line):
                list_items += 1

        # Collapse large arrays (lines starting with "- " at consistent indent)
        result: list[str] = []
        array_count = 0
        array_indent: int | None = None

        for line in lines:
            m = re.match(r"^(\s*)- ", line)
            if m:
                indent = len(m.group(1))
                if array_indent is None:
                    array_indent = indent
                    array_count = 1
                    result.append(line)
                elif indent == array_indent:
                    array_count += 1
                    if array_count <= 3:
                        result.append(line)
                    elif array_count == 4:
                        result.append(f"{' ' * indent}  ... ({array_count} items so far)")
                elif array_count <= 3:
                    result.append(line)
            else:
                # Non-array line — flush array count if needed
                if array_count > 3:
                    # Update the "so far" placeholder with final count
                    for j in range(len(result) - 1, -1, -1):
                        if "items so far" in result[j] or "items total" in result[j]:
                            indent_str = " " * (array_indent or 0)
                            result[j] = f"{indent_str}  ... ({array_count} items total)"
                            break
                array_count = 0
                array_indent = None
                result.append(line)

        # Final flush
        if array_count > 3:
            for j in range(len(result) - 1, -1, -1):
                if "items so far" in result[j] or "items total" in result[j]:
                    indent_str = " " * (array_indent or 0)
                    result[j] = f"{indent_str}  ... ({array_count} items total)"
                    break

        compressed = "\n".join(result)
        if len(compressed) < len(output):
            summary = f"--- ({len(lines)} lines"
            if top_level_keys > 0:
                summary += f", {top_level_keys} top-level keys"
            summary += ") ---"
            return summary + "\n" + compressed

        keep_head = 20
        keep_tail = 10
        result_lines = lines[:keep_head]
        result_lines.append(f"\n... ({len(lines) - keep_head - keep_tail} lines truncated) ...\n")
        result_lines.extend(lines[-keep_tail:])
        return "\n".join(result_lines)
