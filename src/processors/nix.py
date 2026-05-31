"""Nix processor: nix build/develop/eval/run, nix-build, nix-shell."""

import re

from .base import Processor

_NIX_CMD_RE = re.compile(
    r"\b(nix\s+(build|develop|run|eval|shell|flake\s+\w+)|nix-build|nix-shell|nix-env)\b"
)
_BUILDING_RE = re.compile(r"^\s*building\s+'/nix/store/")
_COPYING_RE = re.compile(r"^\s*copying path\s+'/nix/store/")
_FETCH_RE = re.compile(r"^\s*(downloading|fetching|copying)\b")
_STORE_PATH_RE = re.compile(r"^\s*/nix/store/\S+\s*$")
# Plan/summary lines worth keeping verbatim.
_KEEP_RE = re.compile(
    r"^\s*(these \d+ (derivations|paths)|"
    r"warning:|error:|error \(|hint:|"
    r"would be (built|fetched)|"
    r"\d+ (derivations|paths))",
)
_ERROR_RE = re.compile(r"\b(error|Error|failed|Failed|cannot|panic)\b")


class NixProcessor(Processor):
    priority = 48
    hook_patterns = [
        r"^(nix\s+(build|develop|run|eval|shell|flake\s+\w+)|nix-build|nix-shell|nix-env)\b",
    ]

    @property
    def name(self) -> str:
        return "nix"

    def can_handle(self, command: str) -> bool:
        return bool(_NIX_CMD_RE.search(command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        result: list[str] = []
        building = 0
        copying = 0
        fetching = 0
        store_paths = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if _KEEP_RE.match(stripped) or _ERROR_RE.search(stripped):
                result.append(line)
            elif _BUILDING_RE.match(line):
                building += 1
            elif _COPYING_RE.match(line):
                copying += 1
            elif _FETCH_RE.match(stripped):
                fetching += 1
            elif _STORE_PATH_RE.match(line):
                store_paths += 1
            else:
                result.append(line)

        notes = []
        if building:
            notes.append(f"{building} derivations built")
        if copying:
            notes.append(f"{copying} paths copied")
        if fetching:
            notes.append(f"{fetching} fetched")
        if store_paths:
            notes.append(f"{store_paths} store paths")
        if notes:
            result.append(f"[{', '.join(notes)}]")

        return "\n".join(result) if result else output
