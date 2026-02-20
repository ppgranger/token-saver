# Search Processor

**File:** `src/processors/search.py` | **Priority:** 35 | **Name:** `search`

Handles search tool output.

## Supported Commands

grep -r, rg (ripgrep), ag (the silver searcher), fd, fdfind.

## Strategy

| Tool | Strategy |
|---|---|
| `grep`/`rg`/`ag` | Groups results by file. If a file has > 3 matches: shows first 3 + count. If > 20 files match: shows first 20 + remaining count. Strips binary file warnings. Summary: `342 matches across 47 files`. Short output (< 20 lines) passes through |
| `fd`/`fdfind` | Groups files by directory. If > 10 files per directory: shows extension breakdown. If > 5: shows first 3 + count. Short output (< 20 lines) passes through |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `search_max_per_file` | 3 | Max match lines shown per file |
| `search_max_files` | 20 | Max files shown before truncation |
