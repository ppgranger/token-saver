# Token-Saver

Universal token-saving extension for AI CLI tools.
Compresses verbose command outputs (git, tests, builds, lint, ls...)
without losing any critical information.

Compatible with **Claude Code** and **Gemini CLI**.

## Why

AI assistants in CLI consume tokens on every command output.
A 500-line `git diff`, a `pytest` run with 200 passing tests, an `npm install`
with 80 packages: everything is sent as-is to the model, which only needs
the actionable information (errors, modified files, results).

Token-Saver intercepts these outputs and compresses them before they reach
the model, preserving 100% of useful information.

## How It Works

### Architecture

```
CLI command  -->  Specialized processor  -->  Compressed output
                        |
                  15 processors
                  (git, test, package_list,
                   build, lint, network,
                   docker, kubectl, terraform,
                   env, search, system_info,
                   file_listing, file_content,
                   generic)
```

The engine (`CompressionEngine`) maintains a priority-ordered chain of processors.
The first processor that can handle the command (`can_handle()`) produces the
compressed output. `GenericProcessor` serves as a fallback and always matches last.

After the specialized processor runs, a lightweight cleanup pass (`clean()`)
strips residual ANSI codes and collapses consecutive blank lines.

### Platform Integration

The two platforms use different mechanisms:

**Claude Code** (PreToolUse hook):

```
1. Claude wants to run `git status`
2. PreToolUse hook intercepts the command
3. Rewrites to: python3 wrap.py 'git status'
4. wrap.py executes the original command
5. Compresses the output
6. Claude receives the compressed version
```

Claude Code's PreToolUse hook cannot modify output after execution.
The only way to reduce tokens is to rewrite the command to go through a wrapper
that executes, compresses, and returns the result.

**Gemini CLI** (AfterTool hook):

```
1. Gemini executes the command
2. AfterTool hook receives the raw output
3. Compresses the output
4. Replaces it via {"decision": "deny", "reason": "<compressed output>"}
```

Gemini CLI allows direct output replacement through the deny/reason mechanism.

### Precision Guarantees

- Short outputs (< 200 characters) are **never** modified
- Compression is only applied if the gain exceeds 10%
- All errors, stack traces, and actionable information are **fully preserved**
- Only "noise" is removed: progress bars, passing tests, installation logs, ANSI codes, platform lines
- 217 unit tests including 24 precision-specific tests that verify every critical piece of data survives compression

## Installation

### Prerequisites

- Python 3.10+
- Claude Code and/or Gemini CLI

### Quick Install

```bash
cd extension
python3 install.py --target claude    # For Claude Code
python3 install.py --target gemini    # For Gemini CLI
python3 install.py --target both      # For both
```

### Development Mode

```bash
python3 install.py --target claude --link   # Symlinks instead of copies
```

Changes in the source directory are immediately applied.

### Uninstall

```bash
python3 install.py --uninstall --target claude
```

### What the Installer Does

1. Copies (or symlinks) files to:
   - Claude Code: `~/.claude/plugins/token-saver/`
   - Gemini CLI: `~/.gemini/extensions/token-saver/`
2. Replaces `{{EXTENSION_DIR}}` in `hooks.json` with the actual path
3. Registers hooks in `~/.claude/settings.json` (Claude Code only)

## Processors

Each processor handles a family of commands. The first one that matches
(`can_handle()`) processes the output.

### 1. Git (`git.py`)

| Command | Strategy |
|---|---|
| `git status` | Condensed: branch, counters by type (M, A, D, ?), files grouped by directory. More than 8 files in a directory: collapsed with breakdown |
| `git diff` | Preserves all filenames, hunk headers, and change lines (+/-). Strips `index` and `---`/`+++` headers (redundant). Reduces context lines to 3 before/after each change. Truncates hunks beyond 150 lines |
| `git diff --stat` | Strips visual bars (`+++---`), keeps filenames and change counts |
| `git log` | Compact one-line format (`hash message`), max 20 entries |
| `git show` | Compact header + compressed diff |
| `git push/pull/fetch/clone` | Strips progress bars and counters, keeps only the result |
| `git branch` | If > 30 branches: current branch + first 5 + counter |
| `git stash list` | Truncates beyond 10 entries |
| `git reflog` | Truncates beyond 20 entries |

**Before:**
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

### 2. Tests (`test_output.py`)

Supports: pytest, jest, vitest, mocha, cargo test, go test, rspec, phpunit, bun test, npm/yarn/pnpm test.

**Strategy:**
- Passing tests: collapsed into `[N tests passed]`
- Failing tests: **full stack trace preserved**
- Platform, rootdir, plugins lines: removed
- Final summary line: kept

**Before:**
```
======== test session starts ========
platform darwin -- Python 3.12.0
collected 100 items
tests/test_1.py::test_func PASSED
... (97 PASSED lines)
tests/test_db.py::test_migration FAILED
======== FAILURES ========
_____ test_migration _____
    def test_migration():
        db = get_db()
>       db.migrate('v2')
E       MigrationError: column 'email' already exists
E       RuntimeError: migration failed at step 3
======== 1 failed, 97 passed in 12.3s ========
```

**After:**
```
[97 tests passed]
tests/test_db.py::test_migration FAILED
======== FAILURES ========
_____ test_migration _____
    def test_migration():
        db = get_db()
>       db.migrate('v2')
E       MigrationError: column 'email' already exists
E       RuntimeError: migration failed at step 3
======== 1 failed, 97 passed in 12.3s ========
```

### 3. Build (`build_output.py`)

Supports: npm, yarn, pnpm (run/install/build/ci/audit), cargo build/check, make, cmake,
gradle, mvn, ant, pip, poetry, uv, tsc, webpack, vite, esbuild, rollup, next build,
nuxt build, docker build/compose build.

**Strategy:**
- **Success**: `Build succeeded.` + size/timing lines if present + warning count
- **Error**: all error messages preserved with context (stack traces, code pointers)
- **Docker build**: keeps step headers and final result, strips intermediate containers and hashes
- **npm audit**: groups vulnerabilities by severity with package names
- **Removed**: progress bars, installation lines, spinners, download counters, pip `━` bars

### 4. Lint (`lint_output.py`)

Supports: eslint, ruff, flake8, pylint, clippy, rubocop, golangci-lint, stylelint,
prettier --check, biome, mypy.

**Strategy:**
- Groups violations by rule: `no-var: 15 occurrences in 8 files`
- Shows 2 examples per rule (configurable), collapses the rest
- Summary: `20 issues across 2 rules:`
- Handles ESLint block format (file header + indented violations) and inline format

**Before:**
```
/src/file0.ts
  10:0  error  Unexpected var  no-var
  20:0  error  Missing return  consistent-return
/src/file1.ts
  10:1  error  Unexpected var  no-var
  20:1  error  Missing return  consistent-return
... (8 more identical files)
20 problems (20 errors, 0 warnings)
```

**After:**
```
20 issues across 2 rules:
  no-var: 10 occurrences in 10 files
    10:0  error  Unexpected var  no-var
    10:1  error  Unexpected var  no-var
    ... (8 more)
  consistent-return: 10 occurrences in 10 files
    20:0  error  Missing return  consistent-return
    20:1  error  Missing return  consistent-return
    ... (8 more)
20 problems (20 errors, 0 warnings)
```

### 5. Network (`network.py`)

Supports: curl, wget.

| Command | Strategy |
|---|---|
| `curl -v` | Strips TLS handshake, connection lifecycle, boilerplate response headers. Keeps HTTP status, request method, essential headers (Content-Type, Location, Set-Cookie, X-Request-Id), response body |
| `curl` (non-verbose) | Strips progress meter table |
| `wget` | Strips DNS resolution, connection info, progress bars. Keeps HTTP status, Length, save location, final result |

### 6. Docker (`docker.py`)

Supports: docker ps, docker images, docker logs, docker pull/push, docker compose ps/logs.

| Command | Strategy |
|---|---|
| `docker ps` | Drops CONTAINER ID and COMMAND columns. Groups by status (Running/Stopped). Collapses >10 stopped containers |
| `docker images` | Filters out dangling `<none>` images (shows count). Drops IMAGE ID column |
| `docker logs` | Error-focused: keeps first 10 lines (startup), error blocks with context, last 20 lines (recent) |
| `docker pull/push` | Strips layer-by-layer progress, keeps digest and final status |

### 7. Package Listing (`package_list.py`)

Supports: pip list/freeze, npm ls/list, yarn list, pnpm list, conda list, gem list, brew list.

**Strategy:**
- Shows total count + first 15 entries + `... (N more)`
- `npm ls`: collapses dependency tree, shows top-level only, preserves UNMET DEPENDENCY warnings
- Fixes a routing bug where `pip list`/`npm ls` were previously mishandled by the build processor

### 8. Search (`search.py`)

Supports: grep -r, rg, ag.

**Strategy:**
- Groups results by file
- If a file has >3 matches: shows first 3 + count
- If >20 files match: shows first 20 + remaining count
- Strips binary file warnings
- Summary: `342 matches across 47 files`

### 9. Kubernetes (`kubectl.py`)

Supports: kubectl/oc get, describe, logs, top.

| Command | Strategy |
|---|---|
| `kubectl get pods` | If all pods Running/Ready: summarizes as count. Shows only unhealthy pods in detail |
| `kubectl describe` | Strips noise sections (Tolerations, Volumes, QoS, Annotations). Keeps name, namespace, status, container states, Warning events |
| `kubectl logs` | Same as docker logs: error-focused extraction with first/last lines |

### 10. Terraform (`terraform.py`)

Supports: terraform/tofu plan, apply, destroy.

**Strategy:**
- Strips provider initialization and backend configuration
- For create (+): keeps all attributes (they're new)
- For update (~): keeps only changed attributes (with `->`)
- For destroy (-): keeps resource header only
- Always preserves: Plan summary, errors, warnings, output changes, `(known after apply)`, `forces replacement`

### 11. Environment (`env.py`)

Supports: env, printenv, set.

**Strategy:**
- Filters system variables (TERM, SHELL, USER, HOME, LANG, LC_*, SSH_*, XDG_*, DISPLAY, etc.)
- **Redacts sensitive values**: variables matching `*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*` show `VAR=***`
- Truncates long PATH-like values to first 3 entries + count
- Summary: `87 environment variables (23 application-relevant)`

### 12. System Info (`system_info.py`)

Supports: du, wc, df.

| Command | Strategy |
|---|---|
| `du` | Sorts by size descending, shows top 15 entries + total |
| `wc` | Sorts by count descending, shows top 15 + total. Counts zero-entry files separately |
| `df` | Strips snap/loop/squashfs/devtmpfs mounts. Keeps tmpfs only for `/tmp` |

### 13. File Listing (`file_listing.py`)

| Command | Strategy |
|---|---|
| `ls` | > 20 items: grouped by extension with counts |
| `ls -l` | > 50 items: truncated with count |
| `find` | > 30 results: grouped by directory, > 20 files per directory: extension breakdown |
| `tree` | > 50 lines: middle truncated, summary line preserved |

### 14. File Content (`file_content.py`)

Content-aware compression for `cat`, `head`, `tail`, `bat`, `less`, `more`. Instead of blind head/tail truncation, the processor detects the content type and applies a specialized strategy.

| Content Type | Detection | Strategy |
|---|---|---|
| **Code** (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.tf`, etc.) | File extension | Keeps imports/headers (first 20 lines), function/class signatures + 3 body lines, TODO/FIXME/HACK markers. Summary: `(N total lines, M definitions found)` |
| **Config** (`.json`, `.yaml`, `.toml`, `.xml`, `.ini`, `.env`, etc.) | File extension | JSON: parsed top-level structure with truncated values/arrays. YAML: keeps indent ≤2 lines. INI/TOML: keeps `[section]` headers and key=value lines |
| **Logs** | Extension or heuristic (>30% lines match timestamp/loglevel patterns) | Keeps first 5 + last 5 lines (temporal context), ERROR/WARN/FATAL with ±2 context lines, counts INFO/DEBUG lines |
| **CSV/TSV** (`.csv`, `.tsv`) | Extension or heuristic (consistent separators) | Header + 5 first data rows + 3 last rows + `(N data rows, M columns)` |
| **Unknown** | Fallback | Head/tail truncation: first 150 + last 50 lines (original behavior) |

### 15. Generic (`generic.py`) -- Fallback

Applies to any command not recognized by specialized processors.

- ANSI code stripping (colors, formatting, OSC sequences)
- Progress bar stripping (lines that are mostly `━`, `█`, `#`, `=` characters)
- Consecutive blank lines merged into one
- Consecutive identical lines collapsed: `line (x47)`
- Consecutive similar lines (differing only in numbers) collapsed: keeps first + last + count. Targets curl/wget progress output while preserving meaningful data
- Middle truncation if > 500 lines (keeps 200 + 100)

The `GenericProcessor` also serves as a second-pass cleaner (`clean()`)
after each specialized processor, applying only ANSI stripping and
blank line merging (no dedup or truncation).

## Configuration

Thresholds are configurable via JSON file or environment variables.

### Configuration File

`~/.token-saver/config.json`:

```json
{
  "enabled": true,
  "min_input_length": 200,
  "min_compression_ratio": 0.10,
  "max_diff_hunk_lines": 150,
  "max_log_entries": 20,
  "max_file_lines": 300,
  "generic_truncate_threshold": 500,
  "debug": false
}
```

### Environment Variables

Every key can be overridden with the `TOKEN_SAVER_` prefix:

```bash
export TOKEN_SAVER_MAX_LOG_ENTRIES=50
export TOKEN_SAVER_DEBUG=true

# Disable compression entirely (bypass mode)
export TOKEN_SAVER_ENABLED=false
```

### Complete Parameter List

| Parameter | Default | Description |
|---|---|---|
| `enabled` | true | Master switch — set to `false` to bypass all compression |
| `min_input_length` | 200 | Minimum threshold (characters) to attempt compression |
| `min_compression_ratio` | 0.10 | Minimum gain (10%) to apply compression |
| `wrap_timeout` | 300 | Wrapper timeout in seconds |
| `max_diff_hunk_lines` | 150 | Max lines per hunk in git diff |
| `max_diff_context_lines` | 3 | Context lines kept before/after each change in diffs |
| `max_log_entries` | 20 | Max entries in git log |
| `max_file_lines` | 300 | Threshold before file content compression kicks in |
| `file_keep_head` | 150 | Lines kept from the start of file (fallback strategy) |
| `file_keep_tail` | 50 | Lines kept from the end of file (fallback strategy) |
| `file_code_head_lines` | 20 | Import/header lines to preserve in code files |
| `file_code_body_lines` | 3 | Body lines kept per function/class definition |
| `file_log_context_lines` | 2 | Context lines around errors in log files |
| `file_csv_head_rows` | 5 | Data rows kept from start of CSV files |
| `file_csv_tail_rows` | 3 | Data rows kept from end of CSV files |
| `generic_truncate_threshold` | 500 | Generic truncation threshold |
| `generic_keep_head` | 200 | Lines kept from the start (generic) |
| `generic_keep_tail` | 100 | Lines kept from the end (generic) |
| `ls_compact_threshold` | 20 | Items before ls compaction |
| `find_compact_threshold` | 30 | Results before find compaction |
| `tree_compact_threshold` | 50 | Lines before tree truncation |
| `lint_example_count` | 2 | Examples shown per lint rule |
| `lint_group_threshold` | 3 | Occurrences before grouping by rule |
| `db_prune_days` | 90 | Stats retention in days |
| `debug` | false | Enable debug logging |

## Savings Tracking

Token-Saver records every compression in a local SQLite database:

```
~/.token-saver/savings.db
```

### Tables

- **savings**: each individual compression (timestamp, command, processor, sizes, platform)
- **sessions**: aggregated totals per session (first/last activity, total original/compressed, command count)

### Automatic Stats

On every session start, the `SessionStart` hook displays a summary:

```
[token-saver] Lifetime: 342 cmds, 1.2 MB saved (67.3%) | Session: 5 cmds, 45.2 KB saved (72.1%)
```

### Manual Stats

You can check your savings at any time with the `stats.py` command:

```bash
python3 src/stats.py
```

```
Token-Saver Statistics
========================================

Session
----------------------------------------
  Commands compressed:  12
  Original size:        245.3 KB
  Compressed size:      62.1 KB
  Saved:                183.2 KB (74.7%)

Lifetime
----------------------------------------
  Sessions:             47
  Commands compressed:  342
  Original size:        1.8 MB
  Compressed size:      589.4 KB
  Saved:                1.2 MB (67.3%)

Top Processors
----------------------------------------
  git                    142 cmds, 487.2 KB saved
  test                    89 cmds, 312.1 KB saved
  build                   45 cmds, 198.7 KB saved
```

For scripting or integration, use `--json`:

```bash
python3 src/stats.py --json
```

### Maintenance

- Auto-pruning of records older than 90 days (configurable)
- Automatic recovery on database corruption
- Thread-safe (reentrant lock on all operations)
- WAL mode for concurrent write performance

## Security

- **No shell injection**: commands are passed through `shlex.quote()` when rewriting
- **Fail-open**: if the hook fails (Python error, missing file), the original command executes normally
- **No sensitive data**: only sizes are stored, not output content
- **Secret redaction**: the `env` processor automatically redacts values of variables matching `*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*` patterns, preventing accidental leakage into AI context windows
- **Signal forwarding**: the wrapper propagates SIGINT/SIGTERM to the child process
- **Exclusions**: commands with pipes, redirections, sudo, editors, ssh are never intercepted
- **Self-protection**: commands containing `token-saver` or `wrap.py` are not intercepted (prevents recursion)

## Project Structure

```
extension/
├── claude/                          # Claude Code specific files
│   ├── plugin.json                  # Claude Code plugin metadata
│   ├── hook_pretool.py              # PreToolUse hook (Claude Code)
│   └── wrap.py                      # CLI wrapper (Claude Code)
├── gemini/                          # Gemini CLI specific files
│   ├── gemini-extension.json        # Gemini extension metadata
│   ├── hooks.json                   # Gemini hook definitions
│   └── hook_aftertool.py            # AfterTool hook (Gemini CLI)
├── src/                             # Shared source code
│   ├── __init__.py
│   ├── config.py                    # Configuration system
│   ├── platforms.py                 # Platform detection + I/O abstraction
│   ├── engine.py                    # Compression engine (orchestrator)
│   ├── hook_session.py              # SessionStart hook (stats, shared)
│   ├── tracker.py                   # SQLite tracking
│   ├── stats.py                     # Stats CLI
│   └── processors/
│       ├── __init__.py
│       ├── base.py                  # Abstract Processor class
│       ├── git.py                   # git status/diff/log/show/push/pull
│       ├── test_output.py           # pytest/jest/cargo test/go test/rspec
│       ├── package_list.py          # pip list/freeze, npm ls, conda list
│       ├── build_output.py          # npm/cargo/make/webpack/tsc/pip
│       ├── lint_output.py           # eslint/ruff/pylint/clippy/mypy
│       ├── network.py               # curl/wget
│       ├── docker.py                # docker ps/images/logs/pull/push
│       ├── kubectl.py               # kubectl get/describe/logs
│       ├── terraform.py             # terraform plan/apply
│       ├── env.py                   # env/printenv (with secret redaction)
│       ├── search.py                # grep -r/rg/ag
│       ├── system_info.py           # du/wc/df
│       ├── file_listing.py          # ls/find/tree
│       ├── file_content.py          # cat/bat (content-aware compression)
│       └── generic.py               # Universal fallback
├── installers/                      # Modular installer package
│   ├── common.py                    # Shared constants + utilities
│   ├── claude.py                    # Claude Code installer
│   └── gemini.py                    # Gemini CLI installer
├── install.py                       # CLI entry point
├── tests/
│   ├── __init__.py
│   ├── test_engine.py               # Engine tests
│   ├── test_processors.py           # Per-processor tests
│   ├── test_hooks.py                # Hook tests
│   ├── test_tracker.py              # SQLite + concurrency tests
│   ├── test_config.py               # Configuration tests
│   └── test_precision.py            # Precision preservation tests
└── README.md
```

## Tests

```bash
cd extension
python3 -m pytest tests/ -v
```

217 tests covering:

- **test_engine.py** (26 tests): compression thresholds, processor priority, ANSI cleanup, multiple calls
- **test_processors.py** (117 tests): each processor with nominal and edge cases, diff context reduction, docker build/ps/images/logs, npm audit, pytest warnings, fuzzy line collapse, progress bar stripping, curl/wget, kubectl, terraform, env, search, system info, package listing, content-aware file compression
- **test_hooks.py** (27 tests): matching patterns, exclusions, subprocess integration, new command patterns (curl, kubectl, terraform, env, grep, system info, package lists)
- **test_tracker.py** (16 tests): CRUD, concurrency (4 threads), corruption recovery, stats CLI (human + JSON output)
- **test_config.py** (6 tests): defaults, env overrides, invalid values
- **test_precision.py** (25 tests): verification that every critical piece of data survives compression (filenames, hashes, error messages, stack traces, line numbers, rule IDs, diff changes, warning types, secret redaction, unhealthy pods, terraform changes, unmet dependencies)

## Debugging

To diagnose issues:

```bash
# Test compression on a command without replacing the output
python3 claude/wrap.py --dry-run 'git status'

# Enable debug logging
export TOKEN_SAVER_DEBUG=true

# Check stats
python3 src/stats.py
```

## Known Limitations

- Does not compress commands with pipes (`git log | head`), redirections (`> file`), or chaining (`&&`, `||`)
- `sudo`, `ssh`, `vim` commands are never intercepted
- Long diff compression truncates per-hunk, not per-file: a diff with many small hunks is not reduced
- The generic processor only deduplicates **consecutive identical lines**, not similar lines
- Gemini CLI: the deny/reason mechanism may have side effects if other extensions use the same hook
