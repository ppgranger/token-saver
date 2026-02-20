# File Listing Processor

**File:** `src/processors/file_listing.py` | **Priority:** 50 | **Name:** `file_listing`

Handles directory listing commands.

## Supported Commands

ls, find, tree, dir, exa, eza.

## Strategy

| Command | Strategy |
|---|---|
| `ls` | > 20 items: grouped by extension with counts |
| `ls -l` | Strips permissions, owner, group, date. Keeps type indicator (directory `/`, symlink), size (human-readable), and name. > 60 items: truncated |
| `exa` / `eza` | Same as `ls` |
| `find` | > 30 results: grouped by directory. > 20 files per directory: extension breakdown |
| `tree` | > 50 lines: middle truncated, summary line (`N directories, M files`) preserved |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `ls_compact_threshold` | 20 | Items before ls compaction |
| `find_compact_threshold` | 30 | Results before find compaction |
| `tree_compact_threshold` | 50 | Lines before tree truncation |
