"""Kubernetes output processor: kubectl get, describe, logs, apply, delete."""

import re

from .. import config
from .base import Processor

# Optional kubectl global options that may appear before the subcommand.
# Covers: -n <ns>, --namespace <ns>, --context <ctx>, --kubeconfig <path>,
#         -A / --all-namespaces, -o <fmt> (when before subcommand)
_KUBECTL_OPTS = (
    r"(?:-n\s+\S+\s+|--namespace(?:=|\s+)\S+\s+"
    r"|--context(?:=|\s+)\S+\s+|--kubeconfig(?:=|\s+)\S+\s+"
    r"|-A\s+|--all-namespaces\s+)*"
)

_KUBECTL_SUBCMDS = r"(get|describe|logs|top|apply|delete|create)"
_KUBECTL_CMD_RE = re.compile(rf"\b(kubectl|oc)\s+{_KUBECTL_OPTS}{_KUBECTL_SUBCMDS}\b")

# Regex to detect "all containers ready": e.g. 1/1, 2/2, 3/3, 10/10
_READY_RE = re.compile(r"\b(\d+)/(\d+)\b")


class KubectlProcessor(Processor):
    priority = 32
    hook_patterns = [
        rf"^(kubectl|oc)\s+{_KUBECTL_OPTS}(get|describe|logs|top|apply|delete|create)\b",
    ]

    @property
    def name(self) -> str:
        return "kubectl"

    def can_handle(self, command: str) -> bool:
        return bool(_KUBECTL_CMD_RE.search(command))

    def _get_subcmd(self, command: str) -> str | None:
        """Extract the kubectl subcommand, skipping any global options."""
        m = _KUBECTL_CMD_RE.search(command)
        return m.group(2) if m else None

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        subcmd = self._get_subcmd(command)
        if subcmd == "describe":
            return self._process_describe(output)
        if subcmd == "logs":
            return self._process_logs(output)
        if subcmd in ("get", "top"):
            return self._process_get(output)
        if subcmd in ("apply", "delete", "create"):
            return self._process_mutate(output)
        return output

    def _is_all_ready(self, line: str) -> bool:
        """Check if a pod line shows all containers ready (e.g. 2/2, 10/10)."""
        m = _READY_RE.search(line)
        if m:
            return m.group(1) == m.group(2)
        return False

    def _strip_column(self, header: str, lines: list[str], col_name: str) -> tuple[str, list[str]]:
        """Remove a column by name from tabular output."""
        m = re.search(rf"\b{col_name}\b", header)
        if not m:
            return header, lines
        col_start = m.start()
        # Find end: next column start or end of line
        rest = header[m.end() :]
        next_col = re.search(r"\S", rest)
        col_end = m.end() + next_col.start() if next_col else len(header)

        new_header = header[:col_start] + header[col_end:]
        new_lines = []
        for line in lines:
            if len(line) >= col_end:
                new_lines.append(line[:col_start] + line[col_end:])
            elif len(line) > col_start:
                new_lines.append(line[:col_start])
            else:
                new_lines.append(line)
        return new_header, new_lines

    def _process_get(self, output: str) -> str:
        """Compress kubectl get: summarize healthy resources, show unhealthy."""
        lines = output.splitlines()
        if len(lines) <= 10:
            return output

        header = lines[0]
        entries = lines[1:]

        # Strip AGE column (rarely useful for LLM)
        if "AGE" in header:
            header, entries = self._strip_column(header, entries, "AGE")

        # Detect pods vs other resources
        is_pods = "STATUS" in header and "READY" in header

        if not is_pods:
            # Generic tabular output -- just truncate if very long
            if len(entries) > 50:
                result = [header]
                result.extend(entries[:40])
                result.append(f"... ({len(entries) - 40} more resources)")
                return "\n".join(result)
            return "\n".join([header, *entries])

        # Pod output: separate healthy from unhealthy
        healthy = []
        unhealthy = []

        for line in entries:
            stripped = line.strip()
            if not stripped:
                continue
            # Running + all containers ready = healthy
            is_running = re.search(r"\bRunning\b", line)
            is_completed = re.search(r"\bCompleted\b", line)
            all_ready = self._is_all_ready(line)

            if (is_running and all_ready) or is_completed:
                healthy.append(line)
            else:
                unhealthy.append(line)

        result = [header]

        if unhealthy:
            for line in unhealthy:
                result.append(line)

        if healthy:
            if len(healthy) > 5:
                result.append(f"... ({len(healthy)} pods Running/Ready)")
            else:
                result.extend(healthy)

        return "\n".join(result)

    def _process_describe(self, output: str) -> str:
        """Compress kubectl describe: keep key info, strip noise."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        result = []
        skip_section = False
        current_section = ""

        # Top-level keys that are noise
        noise_keys = {
            "tolerations",
            "volumes",
            "qos class",
            "node-selectors",
            "annotations",
            "managed fields",
        }

        # Top-level keys worth keeping -- use exact matching
        keep_keys = {
            "name",
            "namespace",
            "status",
            "state",
            "containers",
            "events",
            "conditions",
            "type",
            "reason",
            "message",
            "last state",
            "restart count",
            "port",
            "image",
            "node",
            "labels",
        }

        for line in lines:
            stripped = line.strip()

            # Top-level key-value lines (no leading whitespace, key: value)
            if re.match(r"^[A-Z][\w\s-]+:", line) and not line.startswith((" ", "\t")):
                key = line.split(":")[0].strip().lower()

                # Check if this starts a noise section
                if key in noise_keys:
                    skip_section = True
                    current_section = key
                    continue

                skip_section = False
                current_section = key

                # Exact match against keep_keys
                if key in keep_keys:
                    result.append(line)
                continue

            if skip_section:
                continue

            # Events section -- keep Warning events, skip Normal
            if current_section == "events":
                if "Warning" in line or "Error" in line or "Failed" in line:
                    result.append(line)
                elif re.match(r"^\s*Type\s+Reason", stripped):
                    result.append(line)  # Keep header
                elif "Normal" in line:
                    continue
                else:
                    result.append(line)
                continue

            # Container state info
            if re.search(
                r"(State|Last State|Restart Count|Exit Code|Reason|Ready|Image):", stripped
            ):
                result.append(line)
                continue

            # Indented content under kept sections
            if line.startswith(("  ", "\t")):
                result.append(line)

        return "\n".join(result)

    def _process_logs(self, output: str) -> str:
        """Compress kubectl logs: keep errors, startup, recent lines."""
        lines = output.splitlines()
        keep_head = config.get("kubectl_keep_head")
        keep_tail = config.get("kubectl_keep_tail")

        if len(lines) <= keep_head + keep_tail:
            return output

        error_lines = []
        for i, line in enumerate(lines):
            if re.search(
                r"\b(error|Error|ERROR|exception|Exception|"
                r"fatal|Fatal|FATAL|panic|Panic)\b",
                line,
            ):
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                for el in lines[start:end]:
                    if el not in error_lines:
                        error_lines.append(el)

        result = lines[:keep_head]
        if error_lines:
            result.append(f"\n... ({len(lines)} total lines, showing errors) ...\n")
            result.extend(error_lines[:40])
        else:
            result.append(f"\n... ({len(lines) - keep_head - keep_tail} lines truncated) ...\n")
        result.extend(lines[-keep_tail:])

        return "\n".join(result)

    def _process_mutate(self, output: str) -> str:
        """Compress kubectl apply/delete/create: keep result lines, skip verbose details."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        for line in lines:
            stripped = line.strip()
            # Resource mutation results, errors, warnings, summaries
            if (
                re.search(r"\b(created|configured|unchanged|deleted|patched)\b", stripped)
                or re.search(r"\b(error|Error|ERROR|warning|Warning)\b", stripped)
                or re.search(r"\d+\s+resource", stripped)
            ):
                result.append(stripped)

        if not result:
            return output
        return "\n".join(result)
