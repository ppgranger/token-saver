# Docker Processor

**File:** `src/processors/docker.py` | **Priority:** 31 | **Name:** `docker`

Handles Docker CLI and Docker Compose output. Supports global options (`--context`, `-H`, `--host`).

## Supported Commands

| Command | Strategy |
|---|---|
| `docker ps` | Drops CONTAINER ID and COMMAND columns. Groups by status (Running/Stopped). Collapses > 10 stopped containers. Detects Exited, Created, and Dead statuses |
| `docker images` | Filters out dangling `<none>` images (shows count). Drops IMAGE ID column |
| `docker logs` | Error-focused: keeps first 10 lines (startup), error blocks with context (2 lines before/after), last 20 lines (recent). Caps error lines at 50 |
| `docker pull/push` | Strips layer-by-layer progress, keeps digest and final status |
| `docker inspect` | Parses JSON, extracts key fields (Id, Name, State, Config, NetworkSettings). Shows State details, Config image/cmd/env, network ports and IPs. Falls back to structure summary for unrecognized keys |
| `docker stats` | Keeps only the last block from streaming output (header + data rows). Static `--no-stream` output passes through |
| `docker compose up` | Keeps Created/Started/Running/Error lines, network/volume creation. Strips progress percentages and log output |
| `docker compose down` | Keeps Stopped/Removed lines and network/volume removal |
| `docker compose build` | Keeps service headers, build step headers, errors, and final result. Strips intermediate containers |
| `docker compose ps` | Same as `docker ps` |
| `docker compose logs` | Same as `docker logs` |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `docker_log_keep_head` | 10 | Lines kept from start of logs |
| `docker_log_keep_tail` | 20 | Lines kept from end of logs |

## Note

`docker build` and `docker compose build` output is handled by the **Build Output Processor** (priority 25), which processes it before Docker (priority 31).
