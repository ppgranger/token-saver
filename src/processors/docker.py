"""Docker output processor: ps, images, logs, pull, push."""

import re

from .base import Processor

# Optional docker global options that may appear before the subcommand.
# Covers: --context <ctx>, -H <host>, --host <host>
_DOCKER_OPTS = (
    r"(?:--context(?:=|\s+)\S+\s+"
    r"|-H\s+\S+\s+|--host(?:=|\s+)\S+\s+)*"
)

_DOCKER_CMD_RE = re.compile(
    rf"\bdocker\s+{_DOCKER_OPTS}(ps|images|logs|pull|push|compose\s+(?:ps|logs))\b"
)


class DockerProcessor(Processor):
    priority = 31
    hook_patterns = [
        rf"^docker\s+{_DOCKER_OPTS}(build|pull|push|images|ps|logs|compose)\b",
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
            return output
        if subcmd == "ps":
            return self._process_ps(output)
        if subcmd == "images":
            return self._process_images(output)
        if subcmd == "logs":
            return self._process_logs(output)
        if subcmd in ("pull", "push"):
            return self._process_pull(output)
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
        stopped = [e for e in result_entries if "Exited" in e or "Created" in e]
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
        if len(lines) <= 50:
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

        keep_head = 10
        keep_tail = 20

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
