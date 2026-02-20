# System Info Processor

**File:** `src/processors/system_info.py` | **Priority:** 36 | **Name:** `system_info`

Handles disk and file counting commands.

## Supported Commands

| Command | Strategy |
|---|---|
| `du` | Sorts by size descending, shows top 15 entries + total. Parses both tab-separated and space-separated formats. Short output (< 15 lines) passes through |
| `wc` | Sorts by count descending, shows top 15 + total. Counts zero-entry files separately. Short output (< 15 lines) passes through |
| `df` | Strips snap/loop/squashfs/devtmpfs mounts. Keeps tmpfs only for `/tmp`. Removes the Filesystem (device) column to reduce noise |
