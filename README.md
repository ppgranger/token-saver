# Token-Saver

[![CI](https://github.com/ppgranger/token-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/ppgranger/token-saver/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Avg Savings](docs/assets/badge-savings.svg)](docs/processors/)

**Cut your AI coding costs by 60-99% on CLI output — without losing a single error message.**

21 specialized processors understand git, pytest, docker, terraform, kubectl, helm, ansible, and more. Each one knows what to keep and what to discard: errors, diffs, and actionable data stay; progress bars, passing tests, and boilerplate go.

Compatible with **Claude Code** and **Gemini CLI**. Zero latency. No LLM calls. Fully deterministic. One install, instant savings.

### Before & After

| Command | Raw Output | Compressed | Savings |
|---------|-----------|------------|---------|
| `git diff` (large refactor) | 2,270 tokens | 909 tokens | **60%** |
| `pytest` (500 tests, 2 failures) | 6,744 tokens | 308 tokens | **95%** |
| `npm install` (220 packages) | 3,844 tokens | 4 tokens | **99%** |
| `terraform plan` (15 resources) | 1,840 tokens | 137 tokens | **93%** |
| `kubectl get pods` (40 pods) | 1,393 tokens | 79 tokens | **94%** |
| `docker compose logs` (4 services) | 3,200 tokens | 480 tokens | **85%** |
| `helm template` (12 manifests) | 2,100 tokens | 210 tokens | **90%** |

> Run `token-saver benchmark <command>` to measure savings on your own workloads.

## Why

Every CLI command your AI assistant runs burns tokens — and most of that output is noise. A 500-line `git diff`, a `pytest` run with 200 passing tests, an `npm install` with 80 packages: the model only needs errors, modified files, and results. Everything else is wasted context and wasted money.

Token-Saver sits between the CLI and your AI assistant, compressing output with content-aware strategies. The model sees exactly what it needs — nothing more, nothing less. Your context window stays clean, your costs drop, and your assistant responds faster with less noise to process.

## How It Compares

Token-Saver takes a different approach from LLM-based or caching solutions — see the [full comparison](docs/comparison.md).

## How It Works

### Architecture

```
CLI command  -->  Specialized processor  -->  Compressed output
                        |
                  21 processors
                  (git, test, package_list,
                   build, lint, network,
                   docker, kubectl, terraform,
                   env, search, system_info,
                   gh, db_query, cloud_cli,
                   ansible, helm, syslog,
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

Compression is aggressive on noise, conservative on signal:

- Short outputs (< 200 characters) are **never** modified
- Compression is only applied if the gain exceeds 10%
- All errors, stack traces, and actionable information are **fully preserved**
- Source code files (`cat *.py`, `cat *.ts`, ...) pass through **unchanged** — the model needs exact content
- Secrets in `.env` files are automatically **redacted** before reaching the model
- Only "noise" is removed: progress bars, passing tests, installation logs, ANSI codes, platform lines
- 567 unit tests including 44 precision-specific tests that verify every critical piece of data survives compression

## Installation

### Prerequisites

- Python 3.10+
- Claude Code and/or Gemini CLI

### Method 1: Claude Code Plugin (recommended)

From the self-hosted marketplace:
```
/plugin marketplace add ppgranger/token-saver
/plugin install token-saver
```

Or test directly from a local clone:
```bash
git clone https://github.com/ppgranger/token-saver.git
claude --plugin-dir ./token-saver
```

### Method 2: Manual installation

```bash
git clone https://github.com/ppgranger/token-saver.git
cd token-saver
python3 install.py --target claude    # Claude Code only
python3 install.py --target gemini    # Gemini CLI only
python3 install.py --target both      # Both platforms
```

The manual installer registers token-saver as a native Claude Code plugin
(equivalent to `/plugin install`). It appears in `/plugin` list and hooks,
skills, and commands are managed natively by Claude Code.

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

### Updating

**Plugin install**: Claude Code handles updates automatically when you refresh the marketplace.

**Manual install**: Run `token-saver update` from anywhere, or:
```bash
cd token-saver && git pull && python3 install.py --target claude
```

**GitHub releases**: Both methods check for new releases via the GitHub API. The `token-saver update` CLI command and the SessionStart hook notification work regardless of install method.

### Upgrading from v1.x to v2.0

If you previously installed token-saver v1.x:
```bash
cd token-saver
git pull
python3 install.py --target claude
```
The installer automatically:
- Removes legacy hooks from `~/.claude/settings.json` (no longer needed)
- Removes the old `~/.claude/plugins/token-saver/` directory
- Installs to the plugin cache as a native Claude Code plugin
- Registers in `enabledPlugins` and `installed_plugins.json`

You can also run `token-saver update` from anywhere to auto-upgrade.

### Avoid dual installation

Do NOT install token-saver via BOTH `/plugin install` AND `python3 install.py`
simultaneously — this could register the plugin twice. Use one method or the other.

To switch from manual to marketplace:
```bash
python3 install.py --uninstall --target claude
/plugin marketplace add ppgranger/token-saver
/plugin install token-saver
```

### What the Installer Does

1. Copies (or symlinks) files to:
   - Core: `~/.token-saver/` (CLI, updater, shared source)
   - Claude Code: `~/.claude/plugins/cache/token-saver-marketplace/token-saver/`
   - Gemini CLI: `~/.gemini/extensions/token-saver/`
2. Registers as a native Claude Code plugin in `installed_plugins.json` and `enabledPlugins`
3. Installs `token-saver` CLI to `~/.local/bin/`
4. Stamps the current version into plugin manifests
5. Cleans up any legacy `token-saving` or v1.x installation

### CLI

After installation, the `token-saver` command is available:

```bash
token-saver version              # Print current version
token-saver stats                # Show savings statistics
token-saver stats --json         # JSON output for scripting
token-saver update               # Check for and apply updates
token-saver benchmark 'git diff' # Measure compression on a command
token-saver benchmark 'pytest' --format json  # JSON output
token-saver benchmark 'git log' --dry-run     # Show processor without executing
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
| 4 | **Python Install** | 24 | pip install, poetry install/update/add, uv pip install, uv sync | [python_install.md](docs/processors/python_install.md) |
| 5 | **Build** | 25 | npm/yarn/pnpm build/install, cargo build, make, cmake, tsc, webpack, vite, next build, turbo, nx, bazel, sbt, mix compile, docker build | [build_output.md](docs/processors/build_output.md) |
| 6 | **Cargo Clippy** | 26 | cargo clippy (multi-line block grouping with span/help preservation) | [cargo_clippy.md](docs/processors/cargo_clippy.md) |
| 7 | **Lint** | 27 | eslint, ruff, flake8, pylint, clippy, mypy, prettier, biome, shellcheck, hadolint, rubocop, golangci-lint | [lint_output.md](docs/processors/lint_output.md) |
| 8 | **Maven/Gradle** | 28 | mvn, ./mvnw, gradle, ./gradlew (download stripping, task noise removal) | [maven_gradle.md](docs/processors/maven_gradle.md) |
| 9 | **Network** | 30 | curl, wget, http/https (httpie) | [network.md](docs/processors/network.md) |
| 10 | **Docker** | 31 | ps, images, logs, pull/push, inspect, stats, compose up/down/build/ps/logs | [docker.md](docs/processors/docker.md) |
| 11 | **Kubernetes** | 32 | kubectl/oc get, describe, logs, top, apply, delete, create | [kubectl.md](docs/processors/kubectl.md) |
| 12 | **Terraform** | 33 | terraform/tofu plan, apply, destroy, init, output, state list/show | [terraform.md](docs/processors/terraform.md) |
| 13 | **Environment** | 34 | env, printenv (with secret redaction) | [env.md](docs/processors/env.md) |
| 14 | **Search** | 35 | grep -r, rg, ag, fd, fdfind | [search.md](docs/processors/search.md) |
| 15 | **System Info** | 36 | du, wc, df | [system_info.md](docs/processors/system_info.md) |
| 16 | **GitHub CLI** | 37 | gh pr/issue/run list/view/diff/checks/status | [gh.md](docs/processors/gh.md) |
| 17 | **Database Query** | 38 | psql, mysql, sqlite3, pgcli, mycli, litecli | [db_query.md](docs/processors/db_query.md) |
| 18 | **Cloud CLI** | 39 | aws, gcloud, az (JSON/table/text output compression) | [cloud_cli.md](docs/processors/cloud_cli.md) |
| 19 | **Ansible** | 40 | ansible-playbook, ansible (ok/skipped counting, error preservation) | [ansible.md](docs/processors/ansible.md) |
| 20 | **Helm** | 41 | helm install/upgrade/list/template/status/history | [helm.md](docs/processors/helm.md) |
| 21 | **Syslog** | 42 | journalctl, dmesg (head/tail with error extraction) | [syslog.md](docs/processors/syslog.md) |
| 22 | **Structured Log** | 45 | stern, kubetail (JSON Lines grouping by level) | [structured_log.md](docs/processors/structured_log.md) |
| 23 | **File Listing** | 50 | ls, find, tree, exa, eza, rsync | [file_listing.md](docs/processors/file_listing.md) |
| 24 | **File Content** | 51 | cat, head, tail, bat, less, more (content-aware: code, config, log, CSV) | [file_content.md](docs/processors/file_content.md) |
| 25 | **Generic** | 999 | Any command (fallback: ANSI strip, dedup, truncation) | [generic.md](docs/processors/generic.md) |

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

### Per-Project Configuration

Drop a `.token-saver.json` in your repository root to override global settings:

```json
{
  "max_diff_hunk_lines": 300,
  "generic_truncate_threshold": 1000,
  "max_log_entries": 50
}
```

Project settings are merged with global settings. Token-Saver walks up parent directories (like `.gitignore` resolution) to find the nearest `.token-saver.json`. Useful for monorepos or projects with atypical output patterns (large Terraform plans, verbose test suites, etc.).

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
| `user_processors_dir` | `~/.token-saver/processors/` | Directory for custom processors |
| `disabled_processors` | `[]` | List of processor names to disable (env: comma-separated) |
| `max_chain_depth` | 3 | Maximum processor chain depth |
| `debug` | false | Enable debug logging |

## Custom Processors

You can extend Token-Saver with your own processors for commands not covered by the built-in 25.

1. Create a Python file with a class inheriting from `src.processors.base.Processor`
2. Implement `can_handle()`, `process()`, `name`, and set `priority`
3. Copy the file to `~/.token-saver/processors/`

```bash
# Example: install the ansible processor
cp examples/custom_processor/ansible_output.py ~/.token-saver/processors/
```

User processors are auto-discovered on every invocation. A broken processor (syntax error, missing import) is skipped with a warning — it never crashes the engine.

See [`examples/custom_processor/`](examples/custom_processor/) for a complete example with documentation.

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
[token-saver] Lifetime: 342 cmds, 307.2k tokens saved (67.3%) | Session: 5 cmds, 11.3k tokens saved (72.1%)
```

If a newer version is available, the notification is appended:

```
[token-saver] Lifetime: 342 cmds, 307.2k tokens saved (67.3%) | Update available: v1.0.1 -> v1.1.0 -- Run: token-saver update
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
  Original tokens:      61.3k tokens
  Compressed tokens:    15.5k tokens
  Saved:                45.8k tokens (74.7%)

Lifetime
----------------------------------------
  Sessions:             47
  Commands compressed:  342
  Original tokens:      461.0k tokens
  Compressed tokens:    147.3k tokens
  Saved:                307.2k tokens (67.3%)

Top Processors
----------------------------------------
  git                    142 cmds, 121.8k tokens saved
  test                    89 cmds, 78.0k tokens saved
  build                   45 cmds, 49.7k tokens saved
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
- **Exclusions**: commands with complex pipes, redirections, sudo, editors, ssh are never intercepted
- **Safe trailing pipes**: simple trailing pipes (`| head`, `| tail`, `| wc`, `| grep`, `| sort`) are allowed
- **Chained commands**: `&&` and `;` chains are supported — each segment is validated individually
- **Self-protection**: commands containing `token-saver` or `wrap.py` are not intercepted (prevents recursion)

## Project Structure

```
token-saver/
├── .claude-plugin/                  # Plugin metadata
│   ├── plugin.json                  # Plugin manifest
│   └── marketplace.json             # Marketplace catalog for distribution
├── hooks/                           # Native hook declarations
│   └── hooks.json                   # Claude Code reads this automatically
├── skills/                          # Agent skills
│   └── token-saver-config/
│       └── SKILL.md
├── commands/                        # Slash commands
│   └── token-saver-stats.md
├── scripts/                         # Python hook scripts
│   ├── __init__.py                  # Package init (prevents namespace conflicts)
│   ├── hook_pretool.py              # PreToolUse hook (Claude Code)
│   ├── wrap.py                      # CLI wrapper (Claude Code)
│   └── hook_session.py              # SessionStart hook wrapper
├── gemini/                          # Gemini CLI specific files
│   ├── gemini-extension.json        # Gemini extension metadata
│   ├── hooks.json                   # Gemini hook definitions
│   └── hook_aftertool.py            # AfterTool hook (Gemini CLI)
├── bin/                             # CLI executables
│   ├── token-saver                  # Unix CLI wrapper
│   └── token-saver.cmd              # Windows CLI wrapper
├── src/                             # Shared source code
│   ├── __init__.py                  # Version (__version__)
│   ├── chain_utils.py               # Chained command splitting (&&, ;)
│   ├── cli.py                       # CLI entry point (version/stats/update)
│   ├── config.py                    # Configuration system
│   ├── engine.py                    # Compression engine (orchestrator)
│   ├── hook_session.py              # SessionStart hook (stats + update notif)
│   ├── platforms.py                 # Platform detection + I/O abstraction
│   ├── stats.py                     # Stats display
│   ├── tracker.py                   # SQLite tracking
│   ├── version_check.py             # GitHub update check
│   └── processors/                  # 21 auto-discovered processors
│       ├── __init__.py
│       ├── base.py                  # Abstract Processor class
│       ├── utils.py                 # Shared utilities (diff compression)
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
│       ├── gh.py                    # gh pr/issue/run list/view/diff/checks
│       ├── db_query.py              # psql/mysql/sqlite3/pgcli/mycli/litecli
│       ├── cloud_cli.py             # aws/gcloud/az
│       ├── ansible.py               # ansible-playbook/ansible
│       ├── helm.py                  # helm install/upgrade/list/template/status
│       ├── syslog.py                # journalctl/dmesg
│       ├── file_listing.py          # ls/find/tree/exa/eza/rsync
│       ├── file_content.py          # cat/bat (content-aware compression)
│       └── generic.py               # Universal fallback
├── docs/
│   └── processors/                  # Per-processor documentation
│       ├── ansible.md
│       ├── build_output.md
│       ├── cloud_cli.md
│       ├── db_query.md
│       ├── docker.md
│       ├── env.md
│       ├── file_content.md
│       ├── file_listing.md
│       ├── generic.md
│       ├── gh.md
│       ├── git.md
│       ├── helm.md
│       ├── kubectl.md
│       ├── lint_output.md
│       ├── network.md
│       ├── package_list.md
│       ├── search.md
│       ├── syslog.md
│       ├── system_info.md
│       ├── terraform.md
│       └── test_output.md
├── installers/                      # Modular installer package
│   ├── common.py                    # Shared constants + utilities
│   ├── claude.py                    # Claude Code installer (native plugin registration)
│   └── gemini.py                    # Gemini CLI installer
├── install.py                       # Installer entry point
├── CLAUDE.md                        # Plugin instructions
├── tests/
│   ├── test_engine.py               # Engine + registry tests (28)
│   ├── test_processors.py           # Per-processor tests (263)
│   ├── test_hooks.py                # Hook pattern + integration tests (77)
│   ├── test_precision.py            # Precision preservation tests (44)
│   ├── test_tracker.py              # SQLite + concurrency tests (20)
│   ├── test_config.py               # Configuration tests (6)
│   ├── test_version_check.py        # Version check + fail-open tests (12)
│   ├── test_cli.py                  # CLI subcommand tests (7)
│   └── test_installers.py           # Installer utility tests (21)
├── audit_compression.py             # Deep audit tool for compression analysis
├── pyproject.toml                   # Python project config + Ruff rules
├── CONTRIBUTING.md                  # Developer guide
├── LICENSE                          # Apache 2.0
└── README.md
```

## Tests

```bash
python3 -m pytest tests/ -v
```

567 tests covering:

- **test_engine.py** (28 tests): compression thresholds, processor priority, ANSI cleanup, generic fallback, hook pattern coverage for 85+ commands
- **test_processors.py** (306 tests): each processor with nominal and edge cases, chained command routing, all subcommands (blame, inspect, stats, compose, apply/delete, init/output/state, fd, exa, httpie, dotnet/swift/mix test, shellcheck/hadolint/biome, traceback truncation, ansible, helm, syslog, parameterized tests, coverage, docker compose logs, tsc typecheck, .env redaction, minified files, search directory grouping, git lockfiles/stat grouping)
- **test_hooks.py** (79 tests): matching patterns for all supported commands, exclusions (pipes, sudo, editors, redirections, remote rsync), subprocess integration, global options (git, docker, kubectl), chained commands, safe trailing pipes
- **test_precision.py** (44 tests): verification that every critical piece of data survives compression (filenames, hashes, error messages, stack traces, line numbers, rule IDs, diff changes, warning types, secret redaction, unhealthy pods, terraform changes, unmet dependencies)
- **test_tracker.py** (23 tests): CRUD, concurrency (4 threads), corruption recovery, session tracking, stats CLI
- **test_config.py** (11 tests): defaults, env overrides, invalid values
- **test_version_check.py** (12 tests): version parsing, comparison, fail-open on errors
- **test_cli.py** (11 tests): version/stats/help subcommands, bin script execution
- **test_installers.py** (46 tests): version stamping, legacy migration, CLI install/uninstall

## Debugging

To diagnose issues:

```bash
# Test compression on a command without replacing the output
python3 scripts/wrap.py --dry-run 'git status'

# Enable debug logging
export TOKEN_SAVER_DEBUG=true

# Check stats
token-saver stats

# Check version
token-saver version
```

## Known Limitations

- Does not compress commands with complex pipelines, redirections (`> file`), or `||` chains
- Simple trailing pipes are supported (`| head`, `| tail`, `| wc`, `| grep`, `| sort`, `| uniq`, `| cut`)
- Chained commands (`&&`, `;`) are supported — each segment is validated individually
- `sudo`, `ssh`, `vim` commands are never intercepted; remote `rsync` (with host:path) is excluded but local `rsync` is compressible
- Long diff compression truncates per-hunk, not per-file: a diff with many small hunks is not reduced
- The generic processor only deduplicates **consecutive identical lines**, not similar lines
- Gemini CLI: the deny/reason mechanism may have side effects if other extensions use the same hook
