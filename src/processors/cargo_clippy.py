"""Cargo clippy processor: dedicated Rust clippy lint handling."""

import re
from collections import defaultdict

from .. import config
from .base import Processor

_CLIPPY_CMD_RE = re.compile(r"\bcargo\s+clippy\b")
_WARNING_START_RE = re.compile(r"^warning(?:\[(\S+)\])?:\s+(.+)")
_ERROR_START_RE = re.compile(r"^error(?:\[(\S+)\])?:\s+(.+)")
_SPAN_LINE_RE = re.compile(r"^\s*(-->|\d+\s*\||=\s+)")
_WARNING_SUMMARY_RE = re.compile(r"^warning:\s+.+generated\s+\d+\s+warning")
_FINISHED_RE = re.compile(r"^\s*Finished\s+")
_CHECKING_RE = re.compile(r"^\s*Checking\s+\S+\s+v")
_COMPILING_RE = re.compile(r"^\s*Compiling\s+\S+\s+v")

# Clippy lint categories
_CLIPPY_CATEGORIES = {
    "needless_return": "style",
    "redundant_closure": "style",
    "len_zero": "style",
    "manual_map": "style",
    "single_match": "style",
    "match_bool": "style",
    "collapsible_if": "style",
    "unused_imports": "correctness",
    "unused_variables": "correctness",
    "dead_code": "correctness",
    "unreachable_code": "correctness",
    "needless_borrow": "complexity",
    "unnecessary_unwrap": "complexity",
    "map_unwrap_or": "complexity",
    "clone_on_copy": "perf",
    "large_enum_variant": "perf",
    "box_collection": "perf",
}


def _categorize_lint(rule: str) -> str:
    """Categorize a clippy lint by its rule name."""
    # Strip clippy:: prefix if present
    short = rule.replace("clippy::", "")
    return _CLIPPY_CATEGORIES.get(short, "other")


class CargoClippyProcessor(Processor):
    priority = 26
    chain_to = ["lint"]
    hook_patterns = [
        r"^cargo\s+clippy\b",
    ]

    @property
    def name(self) -> str:
        return "cargo_clippy"

    def can_handle(self, command: str) -> bool:
        return bool(_CLIPPY_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        result: list[str] = []
        checking_count = 0
        compiling_count = 0

        # Parse warnings as multi-line blocks
        warnings_by_rule: dict[str, list[list[str]]] = defaultdict(list)
        error_blocks: list[list[str]] = []
        current_block: list[str] = []
        current_rule: str | None = None
        in_error = False
        current_error: list[str] = []
        finished_lines: list[str] = []
        summary_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            if _CHECKING_RE.match(stripped):
                checking_count += 1
                continue
            if _COMPILING_RE.match(stripped):
                compiling_count += 1
                continue

            # Error start
            if _ERROR_START_RE.match(stripped):
                # Flush current warning block
                if current_rule and current_block:
                    warnings_by_rule[current_rule].append(current_block)
                    current_block = []
                    current_rule = None
                # Start error block
                if in_error and current_error:
                    error_blocks.append(current_error)
                in_error = True
                current_error = [line]
                continue

            # Warning start
            wm = _WARNING_START_RE.match(stripped)
            if wm and not _WARNING_SUMMARY_RE.match(stripped):
                # Flush previous
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                if current_rule and current_block:
                    warnings_by_rule[current_rule].append(current_block)

                rule = wm.group(1) or "other"
                current_rule = rule
                current_block = [line]
                continue

            if _WARNING_SUMMARY_RE.match(stripped):
                if current_rule and current_block:
                    warnings_by_rule[current_rule].append(current_block)
                    current_block = []
                    current_rule = None
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                summary_lines.append(line)
                continue

            if _FINISHED_RE.match(stripped):
                if current_rule and current_block:
                    warnings_by_rule[current_rule].append(current_block)
                    current_block = []
                    current_rule = None
                if in_error and current_error:
                    error_blocks.append(current_error)
                    in_error = False
                    current_error = []
                finished_lines.append(line)
                continue

            # Context lines (spans, code, help annotations)
            if in_error:
                current_error.append(line)
            elif current_rule:
                current_block.append(line)

        # Flush remaining
        if in_error and current_error:
            error_blocks.append(current_error)
        if current_rule and current_block:
            warnings_by_rule[current_rule].append(current_block)

        # Build compressed output
        prep = []
        if checking_count:
            prep.append(f"{checking_count} checked")
        if compiling_count:
            prep.append(f"{compiling_count} compiled")
        if prep:
            result.append(f"[{', '.join(prep)}]")

        # All errors (kept in full)
        for block in error_blocks:
            result.extend(block)

        # Grouped warnings by rule
        example_count = config.get("cargo_warning_example_count")
        group_threshold = config.get("cargo_warning_group_threshold")

        for rule, blocks in sorted(warnings_by_rule.items(), key=lambda x: -len(x[1])):
            count = len(blocks)
            category = _categorize_lint(rule)
            if count >= group_threshold:
                result.append(f"warning[{rule}] ({category}): {count} occurrences")
                for block in blocks[:example_count]:
                    result.extend(f"  {bline}" for bline in block)
                if count > example_count:
                    result.append(f"  ... ({count - example_count} more)")
            else:
                for block in blocks:
                    result.extend(block)

        result.extend(summary_lines)
        result.extend(finished_lines)

        return "\n".join(result) if result else output
