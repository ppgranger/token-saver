# Token-Saver

Universal token-saver extension for AI CLI tools.
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

When a specialized processor doesn't achieve the minimum compression ratio (10%),
the engine tries the generic processor as a fallback before returning uncompressed output.

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
- 336 unit tests including precision-specific tests that verify every critical piece of data survives compression

## Installation

### Prerequisites

- Python 3.10+
- Claude Code and/or Gemini CLI

### Quick Install

```bash
python3 install.py --target claude    # For Claude Code
python3 install.py --target gemini    # For Gemini CLI
python3 install.py --target both      # For both
```

The repo/zip can be deleted after installation. Token-Saver copies everything
it needs to `~/.token-saver/` and the platform plugin directories.

### Development Mode

```bash
python3 install.py --target claude --link   # Symlinks instead of copies
```

Changes in the source directory are immediately applied.
Do **not** delete the repo in this mode.

### Uninstall

```bash
python3 install.py --uninstall              # Remove from all platforms
python3 install.py --uninstall --keep-data  # Keep stats DB
```

### What the Installer Does

1. Copies (or symlinks) files to:
   - Core: `~/.token-saver/` (CLI, updater, shared source)
   - Claude Code: `~/.claude/plugins/token-saver/`
   - Gemini CLI: `~/.gemini/extensions/token-saver/`
2. Registers hooks in `~/.claude/settings.json` (Claude Code only)
3. Installs `token-saver` CLI to `~/.local/bin/`
4. Stamps the current version into plugin manifests
5. Cleans up any legacy `token-saving` installation

### CLI

After installation, the `token-saver` command is available:

```bash
token-saver version              # Print current version
token-saver stats                # Show savings statistics
token-saver stats --json         # JSON output for scripting
token-saver update               # Check for and apply updates
```

If `~/.local/bin` is not in your PATH, the installer prints instructions.

## Processors

Each processor handles a family of commands. The first one that matches
(`can_handle()`) processes the output. Detailed documentation for each
processor is in [`docs/processors/`](docs/processors/).

| # | Processor | Priority | Commands | Docs |
|---|---|---|---|---|
| 1 | **Package List** | 15 | pip list/freeze, npm ls, conda list, gem list, brew list | [package_list.md](docs/processors/package_list.md) |
| 2 | **Git** | 20 | status, diff, log, show, push/pull/fetch, branch, stash, reflog, blame, cherry-pick, rebase, merge | [git.md](docs/processors/git.md) |
| 3 | **Test** | 21 | pytest, jest, vitest, mocha, cargo test, go test, rspec, phpunit, bun test, npm/yarn/pnpm test, dotnet test, swift test, mix test | [test_output.md](docs/processors/test_output.md) |
| 4 | **Build** | 25 | npm/yarn/pnpm build/install, cargo build, make, cmake, gradle, mvn, pip install, tsc, webpack, vite, next build, turbo, nx, bazel, sbt, mix compile, docker build | [build_output.md](docs/processors/build_output.md) |
| 5 | **Lint** | 27 | eslint, ruff, flake8, pylint, clippy, mypy, prettier, biome, shellcheck, hadolint, rubocop, golangci-lint | [lint_output.md](docs/processors/lint_output.md) |
| 6 | **Network** | 30 | curl, wget, http/https (httpie) | [network.md](docs/processors/network.md) |
| 7 | **Docker** | 31 | ps, images, logs, pull/push, inspect, stats, compose up/down/build/ps/logs | [docker.md](docs/processors/docker.md) |
| 8 | **Kubernetes** | 32 | kubectl/oc get, describe, logs, top, apply, delete, create | [kubectl.md](docs/processors/kubectl.md) |
| 9 | **Terraform** | 33 | terraform/tofu plan, apply, destroy, init, output, state list/show | [terraform.md](docs/processors/terraform.md) |
| 10 | **Environment** | 34 | env, printenv (with secret redaction) | [env.md](docs/processors/env.md) |
| 11 | **Search** | 35 | grep -r, rg, ag, fd, fdfind | [search.md](docs/processors/search.md) |
| 12 | **System Info** | 36 | du, wc, df | [system_info.md](docs/processors/system_info.md) |
| 13 | **File Listing** | 50 | ls, find, tree, exa, eza | [file_listing.md](docs/processors/file_listing.md) |
| 14 | **File Content** | 51 | cat, head, tail, bat, less, more (content-aware: code, config, log, CSV) | [file_content.md](docs/processors/file_content.md) |
| 15 | **Generic** | 999 | Any command (fallback: ANSI strip, dedup, truncation) | [generic.md](docs/processors/generic.md) |

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
| `enabled` | true | Master switch -- set to `false` to bypass all compression |
| `min_input_length` | 200 | Minimum threshold (characters) to attempt compression |
| `min_compression_ratio` | 0.10 | Minimum gain (10%) to apply compression |
| `wrap_timeout` | 300 | Wrapper timeout in seconds |
| `max_diff_hunk_lines` | 150 | Max lines per hunk in git diff |
| `max_diff_context_lines` | 3 | Context lines kept before/after each change in diffs |
| `max_log_entries` | 20 | Max entries in git log/reflog |
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
| `search_max_per_file` | 3 | Max match lines shown per file |
| `search_max_files` | 20 | Max files shown in search results |
| `kubectl_keep_head` | 10 | Lines kept from start of kubectl logs |
| `kubectl_keep_tail` | 20 | Lines kept from end of kubectl logs |
| `docker_log_keep_head` | 10 | Lines kept from start of docker logs |
| `docker_log_keep_tail` | 20 | Lines kept from end of docker logs |
| `git_branch_threshold` | 30 | Branches before compaction |
| `git_stash_threshold` | 10 | Stash entries before truncation |
| `max_traceback_lines` | 30 | Max traceback lines before truncation |
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

If a newer version is available, the notification is appended:

```
[token-saver] Lifetime: 342 cmds, 1.2 MB saved (67.3%) | Update available: v1.0.1 -> v1.1.0 -- Run: token-saver update
```

### Manual Stats

```bash
token-saver stats
token-saver stats --json
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
token-saver/
├── claude/                          # Claude Code specific files
│   ├── plugin.json                  # Claude Code plugin metadata
│   ├── hook_pretool.py              # PreToolUse hook (Claude Code)
│   └── wrap.py                      # CLI wrapper (Claude Code)
├── gemini/                          # Gemini CLI specific files
│   ├── gemini-extension.json        # Gemini extension metadata
│   ├── hooks.json                   # Gemini hook definitions
│   └── hook_aftertool.py            # AfterTool hook (Gemini CLI)
├── bin/                             # CLI executables
│   ├── token-saver                  # Unix CLI wrapper
│   └── token-saver.cmd              # Windows CLI wrapper
├── src/                             # Shared source code
│   ├── __init__.py                  # Version (__version__)
│   ├── cli.py                       # CLI entry point (version/stats/update)
│   ├── version_check.py             # GitHub update check
│   ├── config.py                    # Configuration system
│   ├── platforms.py                 # Platform detection + I/O abstraction
│   ├── engine.py                    # Compression engine (orchestrator)
│   ├── hook_session.py              # SessionStart hook (stats + update notif)
│   ├── tracker.py                   # SQLite tracking
│   ├── stats.py                     # Stats display
│   └── processors/                  # 15 auto-discovered processors
│       ├── __init__.py
│       ├── base.py                  # Abstract Processor class
│       ├── package_list.py          # pip list/freeze, npm ls, conda list
│       ├── git.py                   # git status/diff/log/show/blame/push/pull
│       ├── test_output.py           # pytest/jest/cargo/go/dotnet/swift/mix test
│       ├── build_output.py          # npm/cargo/make/webpack/tsc/turbo/nx/docker build
│       ├── lint_output.py           # eslint/ruff/pylint/clippy/mypy/shellcheck/hadolint
│       ├── network.py               # curl/wget/httpie
│       ├── docker.py                # docker ps/images/logs/inspect/stats/compose
│       ├── kubectl.py               # kubectl get/describe/logs/apply/delete/create
│       ├── terraform.py             # terraform plan/apply/init/output/state
│       ├── env.py                   # env/printenv (with secret redaction)
│       ├── search.py                # grep/rg/ag/fd/fdfind
│       ├── system_info.py           # du/wc/df
│       ├── file_listing.py          # ls/find/tree/exa/eza
│       ├── file_content.py          # cat/bat (content-aware compression)
│       └── generic.py               # Universal fallback
├── docs/
│   └── processors/                  # Per-processor documentation
│       ├── git.md
│       ├── test_output.md
│       ├── build_output.md
│       ├── lint_output.md
│       ├── network.md
│       ├── docker.md
│       ├── kubectl.md
│       ├── terraform.md
│       ├── package_list.md
│       ├── search.md
│       ├── env.md
│       ├── system_info.md
│       ├── file_listing.md
│       ├── file_content.md
│       └── generic.md
├── installers/                      # Modular installer package
│   ├── common.py                    # Shared constants + utilities
│   ├── claude.py                    # Claude Code installer
│   └── gemini.py                    # Gemini CLI installer
├── install.py                       # Installer entry point
├── tests/
│   ├── test_engine.py               # Engine + registry tests (28)
│   ├── test_processors.py           # Per-processor tests (165)
│   ├── test_hooks.py                # Hook pattern + integration tests (38)
│   ├── test_precision.py            # Precision preservation tests (25)
│   ├── test_tracker.py              # SQLite + concurrency tests (16)
│   ├── test_config.py               # Configuration tests (6)
│   ├── test_version_check.py        # Version check + fail-open tests (7)
│   ├── test_cli.py                  # CLI subcommand tests (7)
│   └── test_installers.py           # Installer utility tests (15)
└── README.md
```

## Tests

```bash
python3 -m pytest tests/ -v
```

336 tests covering:

- **test_engine.py** (28 tests): compression thresholds, processor priority, ANSI cleanup, generic fallback, hook pattern coverage for 73 commands
- **test_processors.py** (165 tests): each processor with nominal and edge cases, all new subcommands (blame, inspect, stats, compose, apply/delete, init/output/state, fd, exa, httpie, dotnet/swift/mix test, shellcheck/hadolint/biome, traceback truncation)
- **test_hooks.py** (38 tests): matching patterns for all supported commands, exclusions (pipes, sudo, editors, redirections), subprocess integration, global options (git, docker, kubectl)
- **test_precision.py** (25 tests): verification that every critical piece of data survives compression (filenames, hashes, error messages, stack traces, line numbers, rule IDs, diff changes, warning types, secret redaction, unhealthy pods, terraform changes, unmet dependencies)
- **test_tracker.py** (16 tests): CRUD, concurrency (4 threads), corruption recovery, stats CLI
- **test_config.py** (6 tests): defaults, env overrides, invalid values
- **test_version_check.py** (7 tests): version parsing, comparison, fail-open on errors
- **test_cli.py** (7 tests): version/stats/help subcommands, bin script execution
- **test_installers.py** (15 tests): version stamping, legacy migration, CLI install/uninstall

## Debugging

To diagnose issues:

```bash
# Test compression on a command without replacing the output
python3 claude/wrap.py --dry-run 'git status'

# Enable debug logging
export TOKEN_SAVER_DEBUG=true

# Check stats
token-saver stats

# Check version
token-saver version
```

## Known Limitations

- Does not compress commands with pipes (`git log | head`), redirections (`> file`), or chaining (`&&`, `||`)
- `sudo`, `ssh`, `vim` commands are never intercepted
- Long diff compression truncates per-hunk, not per-file: a diff with many small hunks is not reduced
- The generic processor only deduplicates **consecutive identical lines**, not similar lines
- Gemini CLI: the deny/reason mechanism may have side effects if other extensions use the same hook
