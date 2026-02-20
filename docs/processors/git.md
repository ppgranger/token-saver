# Git Processor

**File:** `src/processors/git.py` | **Priority:** 20 | **Name:** `git`

Handles all common git subcommands, including those with global options (`-C`, `--no-pager`, `-c`, `--git-dir`, `--work-tree`).

## Supported Commands

| Command | Strategy |
|---|---|
| `git status` | Condensed: branch info, counters by type (M, A, D, R, C, ?), files grouped by directory. More than 8 files in a directory: collapsed with breakdown. Handles long-format and short-format status, merge conflicts (UU, AA, DD, AU, UA, DU, UD), and `HEAD detached` |
| `git diff` | Preserves all filenames, hunk headers, and change lines (+/-). Strips `index` and `---`/`+++` headers. Reduces context lines to 3 before/after each change. Truncates hunks beyond 150 lines |
| `git diff --stat` | Strips visual bars (`+++---`), keeps filenames and change counts |
| `git diff --name-only` | Groups by directory when > 20 files |
| `git diff --name-status` | Groups by directory when > 20 files |
| `git log` | Compact one-line format (`hash message`), max 20 entries. Detects `--graph` format and preserves ASCII art structure |
| `git show` | Compact header (strips Author/Date/Merge) + compressed diff |
| `git push/pull/fetch/clone` | Strips progress bars and counters, keeps only the result |
| `git branch` | If > 30 branches: current branch + first 5 + counter |
| `git stash list` | Truncates beyond 10 entries |
| `git reflog` | Truncates beyond 20 entries |
| `git blame` | Groups by author with line counts and percentages, shows last 10 lines for context. Short files (< 20 lines) pass through |
| `git cherry-pick/rebase/merge` | Strips progress (counting/compressing objects), keeps result |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `max_diff_hunk_lines` | 150 | Max lines per hunk in git diff |
| `max_diff_context_lines` | 3 | Context lines kept before/after each change |
| `max_log_entries` | 20 | Max entries in git log/reflog |
| `git_branch_threshold` | 30 | Branches before compaction |
| `git_stash_threshold` | 10 | Stash entries before truncation |

## Example

**Before (`git status`):**
```
On branch feature/auth
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
	modified:   src/auth.py
	modified:   src/models.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	src/new_handler.py
	tests/test_auth_new.py

no changes added to commit
```

**After:**
```
On branch feature/auth | no changes added to commit
Files: 4 (?:2, M:2)
  src/M auth.py
  src/M models.py
  src/? new_handler.py
  tests/? test_auth_new.py
```
