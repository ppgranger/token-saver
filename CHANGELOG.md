# Changelog

All notable changes to token-saver are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.2] - 2026-08-09

### Added

- Documented installing token-saver from Anthropic's official community marketplace.
- Scaffolded a GitHub Pages documentation site.

### Changed

- Bumped CI actions to Node 24-compatible versions.

### Fixed

- Closed the residual compression bypasses behind issues #52 and #49.
- Corrected the processor count that had drifted out of sync in the docs.
- Fixed the Jekyll site `<head>`: the custom partial was never included (wrong filename, and minima 2.5.1 has no `custom-head.html` hook, so `_includes/head.html` is now overridden directly).
- Fixed Liquid tags inside an HTML comment breaking the homepage `<head>`, and a nested `{% comment %}` tag that broke the Pages build entirely.

## [2.7.1] - 2026-08-04

### Security

- Stopped redacted secrets from leaking back to the model. The compression-ratio gate could discard a processor's redacted output and fall back to the raw, unredacted input when a short secret didn't shrink the output enough; a second leak re-ran the generic processor on the original unredacted output in the mismatch-fallback path. Both paths are now short-circuited whenever a processor reports a redaction, with regression tests for each.
- Prevented a cloned repository from achieving code execution or disabling secret redaction. `user_processors_dir`, `disabled_processors`, and `redaction_allowlist` are now only honored from the global `~/.token-saver/config.json` or environment variables, never from an auto-discovered project-level `.token-saver.json`.

### Fixed

- `BuildOutputProcessor` no longer reports "Build succeeded." on a failed run whose output lacks a literal "error" (jest's bare `FAIL`, make's `Failure N`, ninja/rollup wording). Processors can now opt into seeing the real exit code as a last-resort signal.
- Fixed false-positive "critical" lines pushing real errors out of capped output. The single case-insensitive matcher (which also matched ordinary words like "Extracting" or "Entry") was split into a case-insensitive vocabulary pattern and a case-sensitive symbol pattern.
- Fixed silently dropped output in chained commands when a segment ended without a trailing newline, gluing the next boundary marker onto the same line and breaking the split.
- Hardened command-eligibility detection: `2>&1`-style file-descriptor duplication is no longer mistaken for a redirection (more commands are eligible), while unquoted background `&`, unquoted non-continuation newlines, and open shell constructs (`for`/`while`/`if`/`case`/`select`) are now excluded. Rewritten commands are syntax-checked with a shell `-n` pass and fall back to the original command if they wouldn't parse.
- Corrected `skills/token-saver-config/SKILL.md`, which documented a nonexistent `token-saver config set` subcommand and four wrong or invented config keys/defaults.
- Fixed the fallback command in `commands/token-saver-stats.md`, which crashed with `ModuleNotFoundError`; it now uses the bundled CLI wrapper.

### Changed

- Regenerated the README's "Complete Parameter List" from the real defaults in `src/config.py`, and added `tests/test_readme_config_sync.py` to fail CI on future drift.
- Replaced the "zero added latency" claim with a measured ~60ms/command overhead, and realigned the Before/After compression table with the figures locked in by the CI ratchet.
- Clarified the `.env` redaction claim: `.env.production`, `.env.local` and similar are redacted; bare `.env`, `.env.example`, and `.env.template` are intentionally untouched.
- Substantially expanded the README with a table of contents, quick start, audience section, per-tool worked examples, a full CLI reference, tuning recipes, an expanded security section, measured performance numbers, an FAQ, and troubleshooting.

## [2.6.3] - 2026-06-02

### Fixed

- Installed all top-level `src` modules by globbing instead of a hardcoded list, so newly added modules are no longer left out of installs.

## [2.6.2] - 2026-05-31

### Fixed

- Resolved ruff CI failures (unused `noqa` directives and formatting drift).

## [2.6.1] - 2026-05-31

### Added

- Seven new content-aware processors, auto-discovered by the registry: pulumi, cdktf, nix, just, mise, act, and bun.
- New shared compression core (`src/core.py`) unifying the compression decision and bookkeeping for both platforms, exposing `should_compress()`, `compress()` (never raises; passes through on error), `audit_log()`, `record_saving()`, `record_mismatches()`, and `record_result()`.
- Bounded output cap (`max_output_bytes`): pathological commands emitting hundreds of MB are truncated to their useful head before compression; a value `<= 0` disables the cap.
- `token-saver explain` command, showing why a command would or wouldn't be compressed (compressible, reason, excluded_by, matched patterns, chain detection) as JSON or text.
- `--show-removed` diff summary for dry-run and benchmark runs, giving a structured breakdown of what compression removed.
- `benchmark --stdin`, reading raw output from stdin instead of executing a subprocess.
- `redaction_allowlist` config key.
- Always-on rotating audit log recording processor and ratio (never output content), plus processor-mismatch events.

### Changed

- Rebranded the second platform integration from Gemini CLI to Antigravity CLI after Google folded Gemini CLI into Antigravity: `gemini/` became `antigravity/` (with `antigravity-plugin.json` and an updated hook path), `installers/gemini.py` became `installers/antigravity.py`, `Platform.GEMINI_CLI` became `Platform.ANTIGRAVITY_CLI` (`antigravity_cli`), and `install.py --target gemini` became `--target antigravity`. The AfterTool deny+reason hook format is unchanged.
- Routed both `scripts/wrap.py` (Claude) and the Antigravity hook through the shared core so the two entry points stay in lock-step.
- `token-saver update` now detects marketplace-managed installs and defers to `/plugin update token-saver`.
- Kept the marker-injection approach to chain compression rather than moving to a linear per-segment pipeline, so shared shell state (`cd`, `export`, variables) and `&&` / `;` short-circuit semantics survive across segments; locked in with regression tests.
- Legacy cleanup of pre-rename `"token-saving"` installs under `~/.gemini/extensions/` was deliberately retained.

### Fixed

- Fixed `cargo clippy` routing, with a regression test.
- Anchored broad `can_handle` patterns to the command position in the `file_content`, `file_listing`, `system_info`, and `search` processors so they no longer match the verb mid-command.
- Guarded against `generic_keep_tail == 0` in `src/processors/generic.py`, where `lines[-0:]` re-emitted the whole list.
- De-duplicated `data_dir()` into a single canonical source.

## [2.5.1] - 2026-05-19

- Maintenance release: version bump to 2.5.1.

## [2.5.0] - 2026-05-16

### Added

- Per-segment compression for chained commands.

## [2.4.2] - 2026-05-14

### Added

- HTML output compression.
- Compression for `docker run` and `docker exec`.

### Changed

- Tightened the context kept around diff hunks.

## [2.4.1] - 2026-05-14

### Added

- `token-saver update` now self-refreshes the installed copy.

## [2.4.0] - 2026-05-14

- Release published without detailed notes.

## [2.3.0] - 2026-04-12

### Added

- Path-prefix normalization so commands invoked through absolute paths (`/usr/bin/git status`), virtualenvs (`.venv/bin/pytest`), local binaries (`./node_modules/.bin/jest`), and version-manager shims (`~/.pyenv/shims/pip`, `~/.nvm/...`, `~/.cargo/bin/cargo`) are detected and compressed.
- Support for commands run through wrapper runners: `npx` (jest, mocha, vitest, playwright, eslint, prettier, stylelint, biome, webpack, vite, esbuild, tsc, next build, turbo run), `poetry run` and `uv run` (pytest, flake8, pylint, ruff, mypy), `pipx run` (pytest), and `bundle exec` (rspec, rails test, rubocop).
- Detection of version-suffixed and full-path Python invocations, such as `python3.11 -m pytest` and `/usr/bin/python3 -m flake8`.
- `python -m pip install` support in the python_install processor.
- Shared `PYTHON_CMD` regex constant in `src/processors/base.py`.

## [2.2.1] - 2026-03-28

### Added

- Cargo processor for `cargo build/check/doc/update/bench`, grouping warnings by type while preserving errors in full.
- Dedicated cargo clippy processor with lint categorization (style, correctness, complexity, perf) that chains to the lint processor.
- Go processor for `go build/vet/mod/generate/install`, collapsing downloads and grouping errors.
- Python install processor for `pip install`, `poetry install`, and `uv pip install`, compressing dependency resolution.
- Maven/Gradle processor collapsing download and compile output.
- SSH processor for non-interactive `ssh` and `scp` with progress compression; the hook exclusion was narrowed to interactive use only.
- jq/yq processor with JSON structure compression and YAML heuristic summarization.
- Structured-log processor for JSON lines, stern, and kubetail output.
- `disabled_processors` config key and environment variable for selectively disabling processors.
- Multi-processor chaining: `chain_to` now accepts lists, with cycle detection and a configurable `max_chain_depth`.

### Changed

- Deduplicated the `poetry.lock` and `Cargo.lock` parsers into a shared `_compress_toml_lock` method.
- Extracted shared Rust compiler regex patterns (`WARNING_START_RE`, `ERROR_START_RE`, and friends) into `utils.py`.

### Fixed

- Restored the missing `@` separator in Pipfile.lock package formatting (`pytest3.11.0` became `pytest@3.11.0`).
- Tightened an overly permissive tree-summary regex in `file_listing` that matched the "director" prefix rather than "directories"/"directory".
- Removed extra newlines in the generic truncation message that produced triple newlines.
- Fixed dead patterns and edge cases in the `build_output` and `lint_output` processors.

## [2.1.1] - 2026-03-17

### Added

- Ansible processor for `ansible-playbook` and `ansible`, summarizing ok/skipped tasks into one line while preserving changed/failed/fatal lines and the full PLAY RECAP.
- Helm processor for `install`, `upgrade`, `list`, `template`, `status`, and `history`, turning template output into a manifest inventory, stripping NOTES boilerplate, and truncating long release lists and histories.
- Syslog processor for `journalctl` and `dmesg`, using head/tail with automatic error extraction and context preservation.
- Lockfile detection in git diffs: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Pipfile.lock`, `Gemfile.lock`, `composer.lock`, `Cargo.lock`, `go.sum`, `poetry.lock`, and `bun.lockb` collapse to a single summary line.
- Directory grouping for `git diff --stat` when more than 20 files changed.
- pytest coverage-table compression, keeping only the TOTAL line and files below 80% coverage.
- Grouping of parameterized test results into a single pass/fail summary listing the failed parameter names.
- Minified file detection: `.min.js`, `.min.css`, and heuristically detected minified files are replaced with a size summary and short preview.
- `.env` variant redaction: sensitive values in `.env.production`, `.env.local`, `.env.staging` and similar (`*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*`, `*AWS_*`) are redacted before reaching the model.
- TypeScript type-check support, grouping `tsc --noEmit` errors by TS error code with counts and examples.
- Service grouping for `docker compose logs`, showing per-service line and error counts, full error lines, and each service's last few lines.
- Directory grouping for `rg`, `grep -r`, and `ag` results spanning more than 30 files.

### Changed

- Raised the network JSON compression threshold from 500 to 1,500 characters so small API responses pass through unchanged.
- Made local `rsync -av src/ dest/` compressible through the file_listing processor; only remote rsync remains excluded.
- Consolidated three independent JSON compression implementations (`network.py`, `cloud_cli.py`, `file_content.py`) into `utils.compress_json_value()`.
- Consolidated three independent log compression implementations (`docker.py`, `kubectl.py`, `file_content.py`) into `utils.compress_log_lines()`, with configurable head/tail sizes, error regex, and context window.
- Resolved SIM103, SIM102, PIE810, and RUF005 ruff warnings, and added PLR0913 to the global ignores for shared utility signatures.

### Fixed

- Fixed the Helm NOTES section leak, where non-indented content lines slipped past the omission logic; everything after `NOTES:` is now stripped.

## [2.0.2] - 2026-03-15

### Changed

- Redesigned the stats visualization with ANSI colors and a per-command breakdown.

## [2.0.1] - 2026-03-09

### Fixed

- Populated the `marketplaces/` directory and pinned the production branch so marketplace installs resolve correctly.

## [2.0.0] - 2026-03-07

### Added

- Native Claude Code plugin support (v2 plugin layout).

### Fixed

- The Claude pretool hook now respects session permissions.

## [1.4.3] - 2026-02-24

### Fixed

- Synced the README and installer with the actual codebase, repairing the install flow.

## [1.4.2] - 2026-02-23

### Added

- Session tracking via `TOKEN_SAVER_SESSION` embedded in rewritten commands, enabling per-session aggregation.
- Allowlist of safe trailing pipes (`head`, `tail`, `grep`, `sort`, `uniq`, `cut`) so those commands stay eligible.
- New shared `src/processors/utils.py` with `compress_diff()`, `compress_json_value()`, and `group_files_by_dir()`.
- Bun support and preserved warning samples in `build_output`; `validate` and `fmt` subcommands in terraform; `api` subcommand routing in `gh`; oxlint, deno lint, golangci-lint, and rubocop parsers in `lint_output`.

### Changed

- Rewrote the file content processor around a two-category dispatch: source code and sensitive config files (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.env`, `.tf`, and ~40 more) now pass through byte-for-byte, eliminating the risk of missing lines causing wrong patches, while lock files, JSON/YAML/TOML/XML, logs, CSV/TSV, and docs each get a structure-preserving strategy.
- Made compression thresholds aggressive by default (`min_input_length=1`, `min_compression_ratio=0.0`), so compression triggers from the first token saved.
- Applied 37 audit fixes across all 15 processors, including deeper key preservation in `cloud_cli` (InstanceId, ResourceName), accurate Jest counts and tighter Go boundary detection in `test_output`, `git status -sb` branch header detection, extensionless file handling in `search`, an inverted wget filter in `network`, stricter psql table detection in `db_query`, shared diff compression in `gh`, and a digit threshold raised to 30% in `generic` to reduce false positives on tabular data.
- The engine now respects explicit processor passthrough: when a processor returns output unchanged, no generic fallback is applied.
- Added a size guard so compression is only reported when the output actually got smaller.

### Fixed

- Fixed a duplicate regex in `build_output`.

## [1.3.1] - 2026-02-21

### Changed

- Report savings in estimated tokens instead of KB/MB, using a configurable ~4 characters-per-token ratio (`chars_per_token` config key or `TOKEN_SAVER_CHARS_PER_TOKEN`). The database still stores raw character counts, so existing data remains valid and is converted at display time.

## [1.2.0] - 2026-02-21

### Added

- GitHub CLI processor for `gh pr list`, `gh issue list`, `gh run view`, `gh pr checks`, `gh pr diff`, and more: passing checks collapse to `[N checks passed]` while failing and pending checks stay in full, long lists truncate after 30 entries, PR diffs reuse the `git diff` context reduction, and PR/issue bodies trim to 20 lines.
- Database query processor for `psql`, `mysql`, `sqlite3`, `pgcli`, `mycli`, and `litecli`: auto-detects PostgreSQL, MySQL, and CSV/TSV formats, keeps the header, first and last rows, and the row-count footer, and passes errors through unmodified.
- Cloud CLI processor for `aws`, `gcloud`, and `az`: recursive depth-limited (depth 4) JSON compression that never truncates resource identifiers (`InstanceId`, `arn`, `Name`, `State`), plus head+tail handling for table and text output.

### Fixed

- Deduplicated `git remote -v` output by merging fetch/push pairs.
- Recognized the `typechange:` prefix in `git status`.
- Intercepted the `set` command in the hook, which `can_handle` matched but `hook_patterns` omitted.
- Intercepted bare `df` and `du` without arguments, which the hook pattern's trailing space had excluded.
- Simplified the `file_listing` and `file_content` `can_handle()` regexes from `re.match(r".*\b...")` to `re.search(r"\b...")`.

## [1.1.1] - 2026-02-20

### Added

- Git: `git blame` grouped by author with line counts and percentages, progress stripping for `cherry-pick`/`rebase`/`merge`, `git stash list` truncation beyond 10 entries, directory grouping for `--name-only`/`--name-status` past 20 files, and merge conflict status codes (UU, AA, DD, AU, UA, DU, UD).
- Docker: structured JSON summary for `docker inspect` (State, Config, NetworkSettings), last-block-only `docker stats`, and Created/Started/Removed/error extraction for `docker compose up/down/build`.
- Kubernetes: result and error extraction for `kubectl apply`, `delete`, and `create`.
- Terraform: provider versions and result kept for `terraform init`, long value truncation for `terraform output`, resource-type grouping for `terraform state list`, and attribute truncation for `terraform state show`.
- Network: httpie (`http`, `https`) support and JSON response compression for API responses over 500 characters.
- Test runners: `dotnet test`, `swift test`, `mix test`, `pnpm test` routed to the Jest handler, and configurable traceback truncation (default 30 lines).
- Linters: `shellcheck` (SC codes), `hadolint` (DL codes), and `biome check/lint` parsing.
- Search: `fd`/`fdfind` results grouped by directory; file listing: `exa`/`eza` support.
- Nine externalized thresholds: `search_max_per_file`, `search_max_files`, `kubectl_keep_head`, `kubectl_keep_tail`, `docker_log_keep_head`, `docker_log_keep_tail`, `git_branch_threshold`, `git_stash_threshold`, and `max_traceback_lines`.
- New `docs/processors/` directory with 15 per-processor documentation files, plus a README processor summary table linking to them.

### Changed

- The engine now falls back to the generic processor when a specialized processor doesn't reach the minimum compression ratio, instead of returning uncompressed output.
- Added `.gitignore` and removed tracked `.DS_Store` files.

### Fixed

- kubectl: replaced the `(\d+)/\1` backreference with an explicit string comparison, which silently failed for pods with more than 9 containers, and replaced `keep_keys` substring matching with exact set membership.
- terraform: subcommand detection is no longer fooled by argument values such as `-var init=true`, and the `terraform init` provider version regex now matches multi-word lines.
- docker: added the missing Dead and Restarting container status detection.
- git log: fixed a `--graph` detection false positive on indented lines.
- Fixed a clippy false positive on `[1 warning]` summary brackets.

## [1.0.0] - 2026-02-20

### Added

- Initial release.
- Yarn Berry and pnpm progress line patterns in `BuildOutputProcessor`.
- Support for global options in hook patterns (`git -C`, `kubectl -n`, and similar).
- LICENSE file.

### Fixed

- Corrected stale `platform.py` references to `platforms.py`.

[2.7.2]: https://github.com/ppgranger/token-saver/compare/v2.7.1...v2.7.2
[2.7.1]: https://github.com/ppgranger/token-saver/compare/v2.6.3...v2.7.1
[2.6.3]: https://github.com/ppgranger/token-saver/compare/v2.6.2...v2.6.3
[2.6.2]: https://github.com/ppgranger/token-saver/compare/v2.6.1...v2.6.2
[2.6.1]: https://github.com/ppgranger/token-saver/compare/v2.5.1...v2.6.1
[2.5.1]: https://github.com/ppgranger/token-saver/compare/v2.5.0...v2.5.1
[2.5.0]: https://github.com/ppgranger/token-saver/compare/v2.4.2...v2.5.0
[2.4.2]: https://github.com/ppgranger/token-saver/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/ppgranger/token-saver/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/ppgranger/token-saver/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/ppgranger/token-saver/compare/v2.2.1...v2.3.0
[2.2.1]: https://github.com/ppgranger/token-saver/compare/v2.1.1...v2.2.1
[2.1.1]: https://github.com/ppgranger/token-saver/compare/v2.0.2...v2.1.1
[2.0.2]: https://github.com/ppgranger/token-saver/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/ppgranger/token-saver/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/ppgranger/token-saver/compare/v1.4.3...v2.0.0
[1.4.3]: https://github.com/ppgranger/token-saver/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/ppgranger/token-saver/compare/v1.3.1...v1.4.2
[1.3.1]: https://github.com/ppgranger/token-saver/compare/v1.2.0...v1.3.1
[1.2.0]: https://github.com/ppgranger/token-saver/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/ppgranger/token-saver/compare/v1.0.0...v1.1.1
[1.0.0]: https://github.com/ppgranger/token-saver/releases/tag/v1.0.0
