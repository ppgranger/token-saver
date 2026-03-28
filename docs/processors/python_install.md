# Python Install Processor

**File:** `src/processors/python_install.py` | **Priority:** 24 | **Name:** `python_install`

Dedicated processor for Python package installation output.

## Supported Commands

pip install, pip3 install, poetry install/update/add, uv pip install, uv sync.

## Strategy

| Tool | Strategy |
|---|---|
| **pip install** | Strip `Collecting` and `Downloading` lines. Remove progress bars. Count packages installed. Show `already satisfied` count. Preserve all errors and warnings. Show installed package summary (first 10 + count) |
| **poetry install/update/add** | Strip `Resolving dependencies` progress. Count installed/updated/removed packages. Show package names with versions. Preserve errors |
| **uv pip install/sync** | Strip download progress. Keep `Resolved N packages` and `Installed N packages` summaries. Preserve errors |

## Exclusions

- `pip list` and `pip freeze` are routed to `PackageListProcessor`

## Configuration

No dedicated configuration keys. Uses default compression thresholds.

## Removed Noise

`Collecting X>=1.0` lines, `Downloading X-1.0.whl` lines, pip progress bars, `Installing collected packages:` line, `Using cached` lines, `Resolving dependencies...` output from poetry.
