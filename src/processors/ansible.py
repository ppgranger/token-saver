"""Ansible output processor: ansible-playbook, ansible."""

import re

from .base import Processor


class AnsibleProcessor(Processor):
    priority = 40
    handles_failure = True
    hook_patterns = [
        r"^ansible(-playbook)?\b",
    ]

    @property
    def name(self) -> str:
        return "ansible"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(ansible-playbook|ansible)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        ok_count = 0
        skipped_count = 0
        in_recap = False

        for line in lines:
            stripped = line.strip()

            # PLAY RECAP is always kept in full
            if stripped.startswith("PLAY RECAP"):
                in_recap = True
                result.append(line)
                continue

            if in_recap:
                result.append(line)
                continue

            # PLAY and TASK headers — keep
            if re.match(r"^(PLAY|TASK)\s+\[", stripped):
                result.append(line)
                continue

            # Separator lines (****)
            if re.match(r"^\*+$", stripped):
                continue

            # changed — always keep
            if re.match(r"^changed:", stripped):
                result.append(line)
                continue

            # failed / fatal / unreachable — always keep
            if re.match(r"^(fatal|failed|unreachable):", stripped, re.I):
                result.append(line)
                continue

            # Error/warning output lines (indented after fatal/failed)
            if re.search(r"\b(ERROR|FAILED|UNREACHABLE|fatal)\b", stripped):
                result.append(line)
                continue

            # "msg:" lines (error messages) — keep
            if re.match(r'^\s*"?msg"?\s*:', stripped):
                result.append(line)
                continue

            # ok — count and skip
            if re.match(r"^ok:", stripped):
                ok_count += 1
                continue

            # skipping — count and skip
            if re.match(r"^skipping:", stripped):
                skipped_count += 1
                continue

            # included/imported — skip
            if re.match(r"^(included|imported):", stripped):
                continue

        # Insert summary at the top
        summary_parts = []
        if ok_count:
            summary_parts.append(f"{ok_count} ok")
        if skipped_count:
            summary_parts.append(f"{skipped_count} skipped")
        if summary_parts:
            result.insert(0, f"[{', '.join(summary_parts)}]")

        return "\n".join(result) if result else output
