"""just processor: compress `just --list` / `--summary` recipe listings.

Only the listing subcommands are handled.  Arbitrary recipe runs (``just
build``) produce the recipe's own output, which we must not touch, so
``can_handle`` deliberately matches listing flags only.
"""

import re

from .base import Processor

_JUST_LIST_RE = re.compile(r"\bjust\b.*\s(--list|-l|--summary)\b")
_RECIPE_RE = re.compile(r"^\s{2,}\S")
_ERROR_RE = re.compile(r"\b(error|Error|failed|Failed)\b")


class JustProcessor(Processor):
    priority = 18
    hook_patterns = [
        r"^just\b.*\s(--list|-l|--summary)\b",
    ]

    @property
    def name(self) -> str:
        return "just"

    def can_handle(self, command: str) -> bool:
        return bool(_JUST_LIST_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 30:
            return output

        recipes: list[str] = []
        other: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _ERROR_RE.search(stripped):
                other.append(line)
            elif _RECIPE_RE.match(line):
                recipes.append(stripped)
            else:
                other.append(line)

        if not recipes:
            return output

        result = list(other)
        result.append(f"{len(recipes)} recipes:")
        result.extend(f"  {r}" for r in recipes[:40])
        if len(recipes) > 40:
            result.append(f"  ... ({len(recipes) - 40} more)")

        return "\n".join(result) if result else output
