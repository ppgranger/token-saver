"""Docker output processor: ps, images, logs, pull, push, inspect, stats, compose."""

import json
import re

from .. import config
from .base import Processor

# Optional docker global options that may appear before the subcommand.
# Covers: --context <ctx>, -H <host>, --host <host>
_DOCKER_OPTS = (
    r"(?:--context(?:=|\s+)\S+\s+"
    r"|-H\s+\S+\s+|--host(?:=|\s+)\S+\s+)*"
)

_DOCKER_CMD_RE = re.compile(
    rf"\bdocker\s+{_DOCKER_OPTS}"
    r"(ps|images|logs|pull|push|inspect|stats|"
    r"compose\s+(?:ps|logs|up|down|build))\b"
)


class DockerProcessor(Processor):
    priority = 31
    hook_patterns = [
        rf"^docker\s+{_DOCKER_OPTS}(pull|push|images|ps|logs|inspect|stats|compose)\b",
    ]

    @property
    def name(self) -> str:
        return "docker"

    def can_handle(self, command: str) -> bool:
        return bool(_DOCKER_CMD_RE.search(command))

    def _get_subcmd(self, command: str) -> str | None:
        """Extract the docker subcommand, skipping any global options."""
        m = _DOCKER_CMD_RE.search(command)
        return m.group(1) if m else None

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        subcmd = self._get_subcmd(command)
        if subcmd and subcmd.startswith("compose"):
            if "ps" in subcmd:
                return self._process_ps(output)
            if "logs" in subcmd:
                return self._process_logs(output)
            if "up" in subcmd:
                return self._process_compose_up(output)
            if "down" in subcmd:
                return self._process_compose_down(output)
            if "build" in subcmd:
                return self._process_compose_build(output)
            return output
        if subcmd == "ps":
            return self._process_ps(output)
        if subcmd == "images":
            return self._process_images(output)
        if subcmd == "logs":
            return self._process_logs(output)
        if subcmd in ("pull", "push"):
            return self._process_pull(output)
        if subcmd == "inspect":
            return self._process_inspect(output)
        if subcmd == "stats":
            return self._process_stats(output)
        return output

    def _process_ps(self, output: str) -> str:
        """Compress docker ps: drop CONTAINER ID and COMMAND columns."""
        lines = output.splitlines()
        if len(lines) <= 2:
            return output

        header = lines[0]
        entries = lines[1:]

        # Parse column positions from header
        col_positions = self._parse_columns(header)
        if not col_positions or "NAMES" not in col_positions:
            return output

        # Extract relevant fields
        result_entries = []
        for line in entries:
            if not line.strip():
                continue
            fields = self._extract_fields(line, col_positions)
            name = fields.get("NAMES", "").strip()
            image = fields.get("IMAGE", "").strip()
            status = fields.get("STATUS", "").strip()
            ports = fields.get("PORTS", "").strip()

            entry = f"  {name}"
            if image:
                entry += f"  ({image})"
            if status:
                entry += f"  {status}"
            if ports:
                entry += f"  {ports}"
            result_entries.append(entry)

        # Group by status
        running = [e for e in result_entries if "Up " in e]
        stopped = [e for e in result_entries if re.search(r"\b(Exited|Created|Dead)\b", e)]
        other = [e for e in result_entries if e not in running and e not in stopped]

        result = [f"{len(entries)} containers:"]
        if running:
            result.append(f"Running ({len(running)}):")
            result.extend(running)
        if stopped:
            if len(stopped) > 10:
                names = ", ".join(s.strip().split()[0] for s in stopped[:5])
                result.append(f"Stopped ({len(stopped)}): {names} ... +{len(stopped) - 5} more")
            else:
                result.append(f"Stopped ({len(stopped)}):")
                result.extend(stopped)
        if other:
            result.extend(other)

        return "\n".join(result)

    def _process_images(self, output: str) -> str:
        """Compress docker images: filter dangling, drop IMAGE ID column."""
        lines = output.splitlines()
        if len(lines) <= 2:
            return output

        header = lines[0]
        entries = lines[1:]

        col_positions = self._parse_columns(header)
        if not col_positions:
            return output

        real_images = []
        dangling_count = 0

        for line in entries:
            if not line.strip():
                continue
            fields = self._extract_fields(line, col_positions)
            repo = fields.get("REPOSITORY", "").strip()
            tag = fields.get("TAG", "").strip()
            size = fields.get("SIZE", "").strip()

            if repo == "<none>" or tag == "<none>":
                dangling_count += 1
                continue

            real_images.append(f"  {repo}:{tag}  {size}")

        result = [f"{len(entries)} images:"]
        if len(real_images) > 30:
            result.extend(real_images[:20])
            result.append(f"  ... ({len(real_images) - 20} more)")
        else:
            result.extend(real_images)
        if dangling_count:
            result.append(f"  ({dangling_count} dangling images)")

        return "\n".join(result)

    def _process_logs(self, output: str) -> str:
        """Compress docker logs: keep errors, first/last lines, collapse repetitions."""
        lines = output.splitlines()
        keep_head = config.get("docker_log_keep_head")
        keep_tail = config.get("docker_log_keep_tail")

        if len(lines) <= keep_head + keep_tail:
            return output

        # Collect error lines and their indices
        error_lines = []
        for i, line in enumerate(lines):
            if re.search(
                r"\b(error|Error|ERROR|exception|Exception|EXCEPTION|"
                r"fatal|Fatal|FATAL|panic|Panic|PANIC|traceback|Traceback)\b",
                line,
            ):
                # Include context: 2 lines before, the error line, 2 after
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                error_lines.extend(lines[start:end])
                if end < len(lines):
                    error_lines.append("")  # separator

        # Deduplicate error context (overlapping windows)
        seen = set()
        unique_errors = []
        for line in error_lines:
            if line not in seen:
                unique_errors.append(line)
                seen.add(line)

        result = lines[:keep_head]
        if unique_errors:
            result.append(f"\n... ({len(lines)} total lines, showing errors) ...\n")
            result.extend(unique_errors[:50])  # Cap error lines
        else:
            result.append(f"\n... ({len(lines) - keep_head - keep_tail} lines truncated) ...\n")
        result.extend(lines[-keep_tail:])

        return "\n".join(result)

    def _process_pull(self, output: str) -> str:
        """Compress docker pull/push: strip layer progress, keep digest and status."""
        lines = output.splitlines()
        result = []

        for line in lines:
            stripped = line.strip()
            # Skip layer progress
            if re.match(
                r"^[0-9a-f]+:\s*(Downloading|Extracting|Pulling|Waiting|"
                r"Verifying|Download complete|Pull complete|Already exists)",
                stripped,
            ):
                continue
            # Skip progress bars
            if re.search(r"\d+(\.\d+)?%", stripped) and re.search(r"\[=*>?\s*\]", stripped):
                continue
            result.append(stripped)

        return "\n".join(result) if result else output

    def _process_inspect(self, output: str) -> str:
        """Compress docker inspect: summarize JSON structure."""
        lines = output.splitlines()
        raw = "\n".join(lines)

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON -- truncate
            if len(lines) > 50:
                return "\n".join(lines[:40]) + f"\n... ({len(lines) - 40} more lines)"
            return output

        if isinstance(data, list) and len(data) == 1:
            data = data[0]

        if not isinstance(data, dict):
            if len(lines) > 50:
                return "\n".join(lines[:40]) + f"\n... ({len(lines) - 40} more lines)"
            return output

        result = []
        # Extract key fields
        important_keys = [
            "Id",
            "Name",
            "State",
            "Config",
            "NetworkSettings",
            "Image",
            "Created",
            "Platform",
            "Status",
        ]

        for key in important_keys:
            if key not in data:
                continue
            val = data[key]
            if isinstance(val, dict):
                # Show top-level keys within the nested dict
                sub_keys = list(val.keys())
                if key == "State":
                    # State is always important -- show all
                    result.append(f"{key}:")
                    for sk, sv in val.items():
                        if isinstance(sv, (str, int, float, bool)):
                            result.append(f"  {sk}: {sv}")
                elif key == "Config":
                    result.append(f"{key}:")
                    for sk in ["Image", "Cmd", "Env", "ExposedPorts", "Labels"]:
                        if sk in val:
                            sv = val[sk]
                            if isinstance(sv, list) and len(sv) > 5:
                                result.append(f"  {sk}: [{len(sv)} items]")
                            elif isinstance(sv, dict) and len(sv) > 5:
                                result.append(f"  {sk}: {{{len(sv)} keys}}")
                            else:
                                sv_str = str(sv)
                                if len(sv_str) > 120:
                                    sv_str = sv_str[:100] + "..."
                                result.append(f"  {sk}: {sv_str}")
                elif key == "NetworkSettings":
                    result.append(f"{key}:")
                    if "Ports" in val:
                        result.append(f"  Ports: {val['Ports']}")
                    if "Networks" in val and isinstance(val["Networks"], dict):
                        for net_name, net_info in val["Networks"].items():
                            ip = net_info.get("IPAddress", "")
                            result.append(f"  {net_name}: {ip}")
                else:
                    result.append(f"{key}: {{{len(sub_keys)} keys}}")
            elif isinstance(val, str):
                if len(val) > 100:
                    result.append(f"{key}: {val[:80]}...")
                else:
                    result.append(f"{key}: {val}")
            else:
                result.append(f"{key}: {val}")

        if not result:
            # No recognized keys -- show top-level structure
            result.append(f"docker inspect: {len(data)} top-level keys")
            for k in list(data.keys())[:15]:
                v = data[k]
                if isinstance(v, dict):
                    result.append(f"  {k}: {{{len(v)} keys}}")
                elif isinstance(v, list):
                    result.append(f"  {k}: [{len(v)} items]")
                else:
                    sv = str(v)
                    if len(sv) > 80:
                        sv = sv[:60] + "..."
                    result.append(f"  {k}: {sv}")

        result.append(f"\n({len(lines)} total lines)")
        return "\n".join(result)

    def _process_stats(self, output: str) -> str:
        """Compress docker stats: keep header + data, strip decoration."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        # docker stats --no-stream produces a header + rows
        # docker stats (streaming) produces repeated blocks
        # Keep only the last block
        header_indices = [
            i for i, line in enumerate(lines) if "CONTAINER" in line and "CPU" in line
        ]
        if header_indices:
            last_header = header_indices[-1]
            return "\n".join(lines[last_header:])

        return output

    def _process_compose_up(self, output: str) -> str:
        """Compress docker compose up: keep created/started/error lines."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        for line in lines:
            stripped = line.strip()
            if (
                re.search(r"(Created|Started|Running|Healthy|Error|error|failed)", stripped, re.I)
                or re.search(r"(Network|Volume)\s+\S+\s+(Created|Found)", stripped)
                or (
                    re.search(r"(Pulling|Building|Creating|Starting)", stripped)
                    and not re.search(r"\d+%", stripped)
                )
            ):
                result.append(stripped)

        if not result:
            return "\n".join(lines[-10:])
        return "\n".join(result)

    def _process_compose_down(self, output: str) -> str:
        """Compress docker compose down: keep stopped/removed lines."""
        lines = output.splitlines()
        if len(lines) <= 15:
            return output

        result = []
        for line in lines:
            stripped = line.strip()
            if re.search(r"(Stopped|Removed|Removing|removed)", stripped, re.I) or re.search(
                r"(Network|Volume)\s+\S+\s+(Removed|removed)", stripped
            ):
                result.append(stripped)

        if not result:
            return "\n".join(lines[-10:])
        return "\n".join(result)

    def _process_compose_build(self, output: str) -> str:
        """Compress docker compose build: keep step headers and results."""
        lines = output.splitlines()
        if len(lines) <= 20:
            return output

        result = []
        for line in lines:
            stripped = line.strip()
            if (
                re.match(r"^\S+\s+(Building|building)", stripped)
                or re.match(r"^(Step \d+/\d+|#\d+\s|\[\d+/\d+\])", stripped)
                or re.search(r"\b(error|Error|ERROR|failed|FAILED)\b", stripped)
                or re.search(r"(Successfully|naming to |writing image|DONE)", stripped, re.I)
            ):
                result.append(stripped)

        if not result:
            return "\n".join(lines[-10:])
        return "\n".join(result)

    def _parse_columns(self, header: str) -> dict[str, int]:
        """Parse column start positions from a tabular header line."""
        columns = {}
        for m in re.finditer(r"(\S+(?:\s\S+)*)", header):
            col_name = m.group(1)
            columns[col_name] = m.start()
        return columns

    def _extract_fields(self, line: str, col_positions: dict[str, int]) -> dict[str, str]:
        """Extract field values based on column positions."""
        fields = {}
        sorted_cols = sorted(col_positions.items(), key=lambda x: x[1])
        for i, (name, start) in enumerate(sorted_cols):
            if i + 1 < len(sorted_cols):
                end = sorted_cols[i + 1][1]
            else:
                end = len(line)
            if start < len(line):
                fields[name] = line[start:end]
            else:
                fields[name] = ""
        return fields
