# GitHub CLI Processor

**File:** `src/processors/gh.py` | **Priority:** 37 | **Name:** `gh`

Handles GitHub CLI (`gh`) output.

## Supported Commands

gh pr list, gh issue list, gh run view, gh pr diff, gh pr checks, gh pr status, gh issue view, gh release list, gh workflow list.

## Strategy

| Subcommand | Strategy |
|---|---|
| `list` | Truncates long titles (> 80 chars). Shows first 30 entries, collapses rest with count. Short output (< 15 lines) passes through |
| `view` | Keeps key metadata fields (title, state, author, labels, etc.). Compresses PR/issue body to first 20 lines |
| `checks` | Collapses passing checks into `[N checks passed]`. Shows all failing and pending checks with details |
| `diff` | Applies git-diff-style compression: strips index/---/+++ headers, limits context lines, truncates large hunks |
| `status` | Keeps section headers and items with action indicators (FAIL, OPEN, etc.) |

## Configuration

Uses `max_diff_hunk_lines` and `max_diff_context_lines` from global config for diff compression.
