# Token-Saver

[![CI](https://github.com/ppgranger/token-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/ppgranger/token-saver/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Avg Savings](docs/assets/badge-savings.svg)](docs/processors/)

**Keep the signal. Stop rereading the same failures.**

Token-Saver compresses the terminal output your AI coding assistant reads —
`git diff`, `pytest`, `npm install`, `terraform plan`, `kubectl`, `docker` — to
leave more room for the code, instructions, and next decision. Compression runs
locally, without another model call or an output upload.

**New in v3: [Delta](#delta-changes-between-runs).** Run your tests,
edit, run again: see which failures are new, changed, or unchanged. Fresh
diagnostics keep their full details; repeated ones can become a short inventory,
with details available on demand. Delta is an experimental, opt-in feature in
3.0.0 for supported pytest and Ruff commands in Claude Code.

**36 specialized processors** cover git, pytest, jest, cargo, go, docker,
kubernetes, terraform, pulumi, helm, ansible, aws, gcloud, and more. Their rules
reduce progress logs and boilerplate, with failure fixtures and optional quality
contracts checking important diagnostics.

Ordinary compression supports **Claude Code** and **Antigravity CLI**. It runs
automatically after installation. Results depend on the command and output;
already concise or unsupported output may stay unchanged.

**Why developers use Token-Saver:**

- 💸 **Less output to process** — many benchmark scenarios save 60-99% of estimated output tokens; billing impact depends on your usage and provider.
- 🔁 **See what changed** — opt-in Delta compares repeated pytest/Ruff runs and keeps retained details one command away.
- 🪟 **Bigger effective context** — fit more real work into the same context window.
- 🎯 **Tested preservation** — failure fixtures check important diagnostics; add quality contracts for your own workflows.
- 🔌 **Install once, forget it** — works automatically in the background, no prompts to change.
- 🛡️ **Local compression** — pure regex/parsing with no network calls in the compression path.

---

## Table of Contents

- [Before & After](#before--after)
- [Quick Start](#quick-start)
- [Why Token-Saver Exists](#why-token-saver-exists)
- [Who It's For](#who-its-for)
- [What Gets Compressed — Real Examples](#what-gets-compressed--real-examples)
- [How It Compares](#how-it-compares)
- [How It Works](#how-it-works)
- [Precision Guarantees](#precision-guarantees)
- [Installation](#installation)
- [CLI Reference](#cli-reference)
- [Delta: Changes Between Runs](#delta-changes-between-runs)
- [Compression Quality Gates](#compression-quality-gates)
- [Processors](#processors)
- [Configuration](#configuration)
- [Tuning Recipes](#tuning-recipes)
- [Custom Processors](#custom-processors)
- [Savings Tracking](#savings-tracking)
- [Security & Privacy](#security--privacy)
- [Performance](#performance)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Project Structure](#project-structure)
- [Tests](#tests)
- [Contributing](#contributing)

---

## Before & After

| Command | Raw Output | Compressed | Savings |
|---------|-----------|------------|---------|
| `git diff` (5 files, 20 context lines each) | 2,270 tokens | 546 tokens | **76%** |
| `git diff --stat` (25 files) | 526 tokens | 21 tokens | **96%** |
| `git log --oneline` (50 entries) | 568 tokens | 117 tokens | **79%** |
| `pytest` (500 tests, 2 failures) | 6,744 tokens | 307 tokens | **95%** |
| `pytest` (200 passed, 30 warnings) | 3,543 tokens | 80 tokens | **98%** |
| `jest` (50 suites, all passing) | 570 tokens | 32 tokens | **94%** |
| `npm install` (220 packages) | 3,843 tokens | 4 tokens | **99.9%** |
| `pip install -r requirements.txt` (30 packages) | 1,797 tokens | 88 tokens | **95%** |
| `cargo build` (120 crates) | 934 tokens | 21 tokens | **98%** |
| `docker build` (20 steps) | 1,682 tokens | 207 tokens | **88%** |
| `curl` download (100 progress lines) | 2,122 tokens | 0 tokens | **100%** |
| `ruff check` (110 violations, 4 rules) | 1,475 tokens | 186 tokens | **87%** |
| `eslint` (55 violations, 2 rules) | 1,292 tokens | 144 tokens | **89%** |
| `tree` (350+ lines) | 1,840 tokens | 136 tokens | **93%** |
| `find . -name '*.py'` (205 results) | 1,294 tokens | 217 tokens | **75%** |

These are locked to [`tests/compression_baselines.json`](tests/compression_baselines.json) and gated by CI ([`tests/test_compression_ratchet.py`](tests/test_compression_ratchet.py)) — if a change makes any of them compress worse, the build fails. Run `python3 scripts/audit_compression.py` to see the full scenario set, or `token-saver benchmark '<command>'` to measure savings on your own workloads.

Not every command compresses, and that's deliberate. `cat large_file.py`, `git status -s`, and `tsc` with 7 type errors all sit in the same baseline file at **0%** — they're already dense, or the model needs them verbatim. Token-Saver returns the original bytes rather than shaving a few tokens at the cost of correctness.

## Quick Start

```
/plugin marketplace add ppgranger/token-saver
/plugin install token-saver
```

(Also available on Anthropic's official community marketplace — see [Installation](#installation) for both options.)

That's the whole setup. Ask Claude to run anything — *"run the tests"*, *"show me the diff"*, *"what changed in the last 10 commits"* — and the output is compressed before it reaches the model. Then:

```bash
token-saver stats
```

Want to see it work before installing it?

```bash
git clone https://github.com/ppgranger/token-saver.git && cd token-saver
python3 bin/token-saver benchmark 'git log --oneline -50'
python3 bin/token-saver benchmark 'git diff' --show-removed
python3 bin/token-saver explain 'docker compose logs | grep error'
```

## Why Token-Saver Exists

Verbose tool output competes with your code and instructions for context. A
`pytest` run with 200 passing tests or an install with hundreds of progress
lines often repeats information that can be represented much more compactly.
After an edit, another run can repeat the same failures too.

Token-Saver reduces that repetition using local parsing. Delta extends this to
consecutive runs, while keeping a current diagnostic inventory and retrievable
details. Whether this improves task completion, response time, or billing needs
measurement in the agent workflow that uses it.

There are three common ways to attack this:

1. **Summarize with another LLM.** Accurate-ish, but it costs a second inference per command, adds seconds of latency, and is non-deterministic — the same `pytest` run can be summarized two different ways.
2. **Truncate blindly.** Free and instant, but it's exactly how you lose the one stack-trace line that mattered.
3. **Parse the format you already know.** `git diff` has a grammar. `pytest` has a summary line. `npm install` has a progress phase and a result phase. Format-aware parsing can remove repetitive output while retaining tested diagnostics, deterministically and without another model call.

Token-Saver is the third approach, applied to 36 command families. It sits
between the CLI and your AI assistant, applying format-specific rules whose
preservation behavior you can test against your own captured output.

## Who It's For

- **Developers paying per token** on Claude Code, whether via API credits or a plan with usage limits. Tool output is often the largest single category of input tokens in an agentic session.
- **Teams running agents in CI**, where a long pipeline command (`terraform plan`, `pytest`, `gradle build`) is piped straight into a model.
- **Anyone hitting context limits** mid-task — the "conversation is too long" wall usually arrives right after a big `npm install` or a wide `git diff`.
- **Monorepo and infrastructure work**, where a single `terraform plan` or `kubectl describe` is thousands of tokens of mostly-unchanged resource attributes.
- **Privacy-sensitive environments** that can't route output through a second model or a hosted service. Token-Saver is pure local Python with no network calls in the compression path.

It's probably **not** for you if your agent mostly reads and writes source files and rarely runs shell commands — file reads go through Claude Code's own Read tool, which Token-Saver doesn't intercept.

## What Gets Compressed — Real Examples

Everything below is actual Token-Saver output, produced by the same scenario corpus the CI ratchet uses.

### `pytest` — 533 lines → 26 lines (95%)

Passing tests collapse to a count. Every failure keeps its full traceback, assertion diff, file, and line number.

```
[500 tests passed]
=================================== FAILURES ===================================
__________________________ test_compression_ratio ______________________________

    def test_compression_ratio():
        engine = CompressionEngine()
        result = engine.compress('git status', large_output)
>       assert len(result[0]) < len(large_output) * 0.5
E       AssertionError: assert 1500 < 1000
...
FAILED tests/test_engine.py::test_compression_ratio - AssertionError: assert 1500 < 1000
FAILED tests/test_processors.py::test_diff_context_trim - AssertionError: assert 42 < 10
========================= 2 failed, 510 passed ==
```

### `ruff check` — 111 lines → 18 lines (87%)

Violations are grouped by rule with a count and a couple of concrete examples, so the model learns the *pattern* to fix instead of reading 45 near-identical lines.

```
110 issues across 4 rules:
  E501: 45 occurrences in 45 files
    src/module/e501_00.py:10:5: E501 Line too long
    src/module/e501_01.py:11:6: E501 Line too long
    ... (43 more)
  F401: 30 occurrences in 30 files
    src/module/f401_00.py:10:5: F401 imported but unused
    ... (28 more)
Found 110 errors.
```

### `npm install` — 526 lines → 1 line (99.9%)

```
Build succeeded.
```

Nothing actionable was lost: the raw output was 220 `added <pkg>@<ver>` lines and a progress bar. Had the install failed, the error and the failing package would survive verbatim — see [Precision Guarantees](#precision-guarantees).

### `cargo build` — 122 lines → 2 lines (98%)

```
[121 crates compiled]
    Finished dev [unoptimized + debuginfo] target(s) in 45.23s
```

### `git diff` — context trimmed, changes untouched (76%)

Unified diffs keep every `+`/`-` line and every `@@` hunk header, with surrounding unchanged context trimmed to `max_diff_context_lines` (default 3):

```
diff --git a/src/module_0.py b/src/module_0.py
@@ -10,30 +10,32 @@ def some_function_0():
     # This is context line 9 that hasn't changed and takes up tokens
-    old_value = compute_something(0)
-    return old_value
+    new_value = compute_something_better(0)
+    cached = cache.get(new_value)
+    if cached:
+        return cached
+    return new_value
     # This is trailing context line 0 that is unchanged and wastes tokens
```

### `tree` — 312 lines → 28 lines (93%)

The directory shape is preserved down to the truncation point, with an explicit marker and the original totals, so the model knows what it *isn't* seeing:

```
.
├── src/
│   ├── engine.py
│   ├── config.py
│   ├── processors/
│   │   ├── git.py
...
... (287 lines truncated)
20 directories, 310 files
```

### `env` / `printenv` — secrets redacted before the model sees them

Variables whose names look sensitive (`SECRET`, `PASSWORD`, `CREDENTIAL`, `API_KEY`, `GITHUB_TOKEN`, and bare `KEY`/`TOKEN`/`AUTH`/`PWD` at letter boundaries — so `PATH`, `AUTHOR`, and `MONKEY` are left alone) have their values replaced. Token-Saver returns this redacted output **even when it isn't smaller** than the input: a redacted result is never traded back for the raw one to satisfy a compression threshold.

## How It Compares

| | Token-Saver | LLM summarizer | Blind truncation | Response caching |
|---|---|---|---|---|
| Extra inference cost | None | One call per command | None | None |
| Additional work | Python startup + parsing | Another model call | Truncation | Cache lookup |
| Deterministic | Yes | No | Yes | Yes |
| Diagnostic preservation | Tested fixtures + configurable quality contracts | Depends on prompt/model | No semantic checks | Depends on cached content |
| Works offline | Yes | Needs a model | Yes | Usually not |
| Understands `git diff` | Yes | Sort of | No | N/A |

For a sourced comparison with RTK and Context Mode, including integration caveats, see the [full comparison](docs/comparison.md).

## How It Works

### Architecture

**Built around explicit SOLID boundaries.** Processors parse output, a shared
policy decides command eligibility, adapters execute commands, and dedicated
modules own storage and presentation. Delta comparison and statistics formatting
are pure functions; engine dependencies and telemetry writers can be supplied
independently. The [architecture guide](docs/architecture.md) documents the
contracts, compatibility guarantees, tests, and remaining couplings.

```
CLI command  -->  Specialized processor  -->  Compressed output
                        |
                  36 processors
                  (git, test, cargo, go, build,
                   lint, package_list, python_install,
                   maven_gradle, bun, network, docker,
                   kubectl, terraform, pulumi, cdktf,
                   nix, mise, env, search, system_info,
                   gh, db_query, cloud_cli, ansible,
                   helm, syslog, ssh, jq_yq, just, act,
                   structured_log, file_listing,
                   file_content, generic)
```

The engine (`CompressionEngine`) maintains a priority-ordered chain of processors.
The first processor that can handle the command (`can_handle()`) produces the
compressed output. `GenericProcessor` serves as a fallback and always matches last.

When a specialized processor doesn't achieve the minimum compression ratio,
the engine tries the generic processor as a fallback before returning uncompressed output.

After the specialized processor runs, a lightweight cleanup pass (`clean()`)
strips residual ANSI codes and collapses consecutive blank lines.

### The Compression Pipeline, Step by Step

1. **Eligibility.** The hook first decides whether the command is safe to wrap at all — see [Security & Privacy](#security--privacy). Redirections, `sudo`, editors, unquoted newlines, background `&`, and shell-construct fragments are all left alone.
2. **Size gates.** Output shorter than `min_input_length` is returned untouched. Output longer than `max_output_bytes` (default 10 MB) is hard-capped with an explicit note before compression, so a pathological command can't be held in memory in full.
3. **Routing.** Processors are tried in priority order; the first `can_handle()` match wins.
4. **Failure routing.** If the command exited non-zero and the matched processor hasn't opted into `handles_failure`, the engine deliberately routes to the generic processor instead. A specialized processor's heuristics are tuned for the *success* shape of a tool's output; failure text often isn't recognized, and an unrecognized line is exactly what a loop drops silently.
5. **Chaining.** A processor may declare `chain_to` to hand its result to a second one, bounded by `max_chain_depth`.
6. **Cleanup.** ANSI escape stripping and blank-line collapsing.
7. **Critical-line recovery.** The engine diffs the compressed output against the original for error-shaped lines that vanished, and re-appends up to `recover_critical_lines` of them under an explicit `[token-saver] N error line(s) recovered` marker. This is a backstop covering all 36 processors — and every future one — rather than an audit that has to be repeated per processor.
8. **Ratio gate.** If the result isn't meaningfully smaller, the original is returned. **Exception:** if the processor redacted secrets, the redacted output always wins, regardless of size.
9. **Tracking.** Sizes — never content — go to a local SQLite database.

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

Because that rewrite is a source-to-source shell transformation, the rewritten
command is syntax-checked (`sh -n -c`) before it runs. If the rewrite wouldn't
parse, the **original** command runs uncompressed — a missed saving, never a
broken command.

**Antigravity CLI** (AfterTool hook):

```
1. Antigravity executes the command
2. AfterTool hook receives the raw output
3. Compresses the output
4. Replaces it via {"decision": "deny", "reason": "<compressed output>"}
```

Antigravity CLI allows direct output replacement through the deny/reason mechanism.

### Chained Commands

`git add -A && git commit -m wip && git push` is a single Bash tool call, but three
commands with three different output shapes. Token-Saver splits the chain, validates
each segment independently, injects unique boundary markers, and compresses each
segment with its own processor — so the `git push` output is handled by the git
processor even though it shares a shell with two other commands. If *any* segment is
ineligible, the whole chain runs untouched.

## Precision Guarantees

Compression is aggressive on noise, conservative on signal:

- Tiny outputs are never touched, and a result that doesn't actually get smaller is discarded in favor of the original (both thresholds are configurable — see [Configuration](#configuration))
- Failure fixtures verify specific errors, tracebacks and changed lines; grouping and bounded recovery can omit other details
- Source code files (`cat *.py`, `cat *.ts`, ...) pass through **unchanged** — the model needs exact content
- Secrets in `.env.production`, `.env.local`, and other `.env.*` variants are automatically **redacted** before reaching the model (`.env`, `.env.example`, and `.env.template` pass through unchanged, by design — see the note below)
- Processors remove or group progress bars, passing tests, installation logs, ANSI codes and other repetitive content according to their documented rules
- Generic truncation includes an omission marker; format-specific processors can also summarize or omit lines
- 1300+ tests including precision-specific tests that verify every critical piece of data survives compression, and a compression-ratchet suite that fails CI if a real-world scenario's compression ratio regresses

Two of these are enforced structurally rather than by convention:

- **`TestFailureHandling`** runs a realistic *failing*-command fixture through **every** processor, at **every** exit code (`0`, `1`, and unknown), and asserts the failure reason is still present. A processor that claims `handles_failure = True` has to earn it; one that doesn't gets routed around.
- **Critical-line recovery** (step 7 above) restores recognized error lines within a configurable cap, except after redaction where restoring raw lines could expose secrets.

These are protections on tested output formats, not a universal lossless guarantee.
Use [quality gates](#compression-quality-gates) to assert the exact diagnostics
your workflow requires.

> **Note on `.env`:** `.env`, `.env.example`, and `.env.template` are intentionally left untouched (not redacted, not compressed) — these are the files you're most likely actively editing, where exact values matter. Other `.env.*` variants (`.env.production`, `.env.local`, ...), which you're more likely to be reading than editing, get their values redacted. If you `cat .env` directly, treat that output as sensitive the same way you would without Token-Saver installed.

## Installation

### Prerequisites

- Python 3.10+
- Claude Code and/or Antigravity CLI

No third-party Python packages are required — Token-Saver uses only the standard library.

### Method 1: Claude Code Plugin (recommended)

Two marketplaces carry Token-Saver — pick one.

**Anthropic's official community marketplace** (`claude-community`), no setup beyond adding it once:
```
/plugin marketplace add anthropics/claude-plugins-community
/plugin install token-saver@claude-community --scope project
```
This mirror is a snapshot pinned to a specific commit, refreshed periodically rather than on every push — if you want the exact latest commit on `main`, use the self-hosted marketplace below instead.

**Self-hosted marketplace** (this repo, always current):
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
python3 install.py --target antigravity    # Antigravity CLI only
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

**GitHub releases**: Both methods check for new releases via the GitHub API. The `token-saver update` CLI command and the SessionStart hook notification work regardless of install method. The remote lookup is cached for 24h and fails open — a network outage or an API rate limit never blocks a session.

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
simultaneously — this could register the plugin twice. Use one method or the
other. The same applies across marketplaces: install from either
`claude-community` or the self-hosted `ppgranger/token-saver` marketplace,
not both.

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
   - Antigravity CLI: `~/.gemini/antigravity-cli/plugins/token-saver/`
2. Registers as a native Claude Code plugin in `installed_plugins.json` and `enabledPlugins`
3. Installs `token-saver` CLI to `~/.local/bin/`
4. Stamps the current version into plugin manifests
5. Cleans up any legacy `token-saving` or v1.x installation

## CLI Reference

After installation the `token-saver` command is available. If `~/.local/bin` is not on your PATH, the installer prints instructions.

| Command | What it does |
|---|---|
| `token-saver version` | Print the installed version |
| `token-saver stats` | Show session + lifetime savings |
| `token-saver stats --json` | Same, machine-readable |
| `token-saver update` | Check GitHub for a new release and apply it |
| `token-saver benchmark '<cmd>'` | Run a command and report its compression |
| `token-saver benchmark '<cmd>' --dry-run` | Show which processor would match, without executing |
| `token-saver benchmark '<cmd>' --show-removed` | Line/byte breakdown of what compression removed |
| `token-saver benchmark '<cmd>' --stdin` | Compress output piped on stdin instead of executing |
| `token-saver benchmark '<cmd>' --format json` | Machine-readable benchmark |
| `token-saver explain '<cmd>'` | Explain how a command is routed — or why it's excluded |
| `token-saver explain '<cmd>' --format json` | Same, machine-readable |
| `token-saver compress '<cmd>'` | Read UTF-8 stdin and emit compressed text; never execute the command label |
| `token-saver compress '<cmd>' --exit-code 1 --max-tokens 1500` | Apply failure-aware routing and check an estimated output budget |
| `token-saver compress '<cmd>' --format json` | Compressed output plus measurements and budget verdict |
| `token-saver replay quality.json` | Check captured fixtures against preservation and budget contracts |
| `token-saver replay quality.json --format json` | Content-free quality report for CI |
| `token-saver delta show RUN` | Read a retained, sanitized Delta snapshot without rerunning its command |
| `token-saver delta show RUN --diagnostic EXACT_ID` | Read full details for one diagnostic in that snapshot |
| `token-saver delta clear` | Delete all retained Delta snapshots and reset comparisons |

`explain` is the fastest way to answer "why didn't that get compressed?":

```console
$ token-saver explain 'git status'
Token-Saver Explain
========================================
Command:      git status
Compressible: yes
Reason:       matched a compressible processor pattern
Processor:    git

$ token-saver explain 'cat x.py > out.txt'
Command:      cat x.py > out.txt
Compressible: no
Reason:       contains output redirection (>, >>, 2>, &>)
Excluded by:  output redirection
Processor:    file_content
```

And `--stdin` lets you test compression against output you already have, with no re-execution:

```bash
pytest > /tmp/out.txt 2>&1
token-saver benchmark 'pytest' --stdin --show-removed < /tmp/out.txt
```

## Delta: Changes Between Runs

**New in 3.0.0: spend context on the next change.** Delta is experimental and
disabled by default.
Delta compares consecutive `pytest` and `ruff check` results in Claude Code so
the agent can see what changed after an edit. Commands still execute normally.
New or changed diagnostics retain their full details; unchanged diagnostics keep
their identity and summary, with a command to retrieve the details locally.

| In your edit–test loop | What Delta reports |
|---|---|
| First supported run | A baseline with full failure details. |
| Same failures again | `UNCHANGED` with names and summaries when that saves output. |
| An assertion or traceback changes | `CHANGED` with its full current details. |
| A new regression appears | `NEW` with its full current details. |
| A previous failure disappears | `PASSED` only with explicit passing evidence; otherwise `NOT OBSERVED`. |
| You need the original diagnostic | `token-saver delta show RUN --diagnostic EXACT_ID`, without rerunning tests. |

One repeated run from the [real-command fixture benchmark](docs/delta.md#run-the-real-command-benchmark)
returns this instead of 4,079 characters of ordinary compressed output
(`RUN` replaces the generated snapshot identifier):

```text
[token-saver delta] pytest | exit 1
3 failed, 21 passed in 0.02s
UNCHANGED test_fixture.py::test_payload — AssertionError: payload diagnostic
UNCHANGED test_fixture.py::test_status — AssertionError: status diagnostic
UNCHANGED test_fixture.py::test_cache — AssertionError: cache diagnostic

Details: token-saver delta show RUN [--diagnostic ID]
```

The complete five-run fixture sequence saves **32.5% of output characters for
pytest and 8.3% for Ruff**, compared with ordinary compression, **including one
targeted detail retrieval**. These are measured fixture results, not universal
savings or billing figures. A complete snapshot read is more expensive: it
erases the gain in the Ruff scenario. The guide includes every result and the
reproduction command.

Enable it explicitly in your global configuration, or before launching Claude:

```bash
export TOKEN_SAVER_DELTA_ENABLED=true
```

The comparison stays within the same session, working directory, and exact
command. Each Delta response includes the current exit status, totals, and diagnostic
inventory. A missing failure is **`NOT OBSERVED`, not confirmed fixed**; `PASSED`
requires an explicit passing test result in the current output. Use `pytest -v`
to expose those per-test results.

Delta is disabled by default. Enabling it retains sanitized output snapshots
locally for 24 hours and at most 100 runs by default. It currently applies only
to supported single commands through the Claude wrapper, with a host session
identifier. Unsupported or ambiguous output uses ordinary compression.

The first run and new or changed failures can produce **more output than v2**
when preserving full details requires it. For unchanged repeats, Token-Saver uses
ordinary sanitized compression whenever Delta would be as large or larger.
Ordinary compression can also win for new failures if it retains every full new
or changed diagnostic. Valid snapshots still establish comparison baselines.
The [reproducible Delta scenario](docs/delta.md#reproduce-the-output-size-benchmark)
compares five synthetic pytest captures, including detail retrieval. It does not
measure agent task success or billing savings; the existing savings table above
still describes ordinary compression.
See the [Delta guide](docs/delta.md) for supported formats, retrieval, storage,
and limits.

## Compression Quality Gates

Make compression testable on **your** workflow: set per-command and total token
budgets, require a minimum measured reduction, and name literal messages that
must survive. `replay` checks saved fixtures without re-running commands; a typo
in a required message fails against the original fixture too.

```bash
python3 bin/token-saver replay examples/quality-replay.json
python3 bin/token-saver compress 'pytest -v' --exit-code 1 --max-tokens 1500 < examples/fixtures/pytest_output.txt
```

An over-budget result returns status `1` and retains the compressed output;
it never truncates more text just to satisfy a limit. Invalid input returns `2`.
Token counts use `ceil(characters / chars_per_token)` and remain estimates,
not exact tokenizer or billing counts. JSON replay reports omit command strings,
raw output and expected text; `compress --format json` includes the compressed output.
Neither command stores captured output or savings history.

See [the manifest format and CI example](docs/quality-gates.md). These additions
are available in this checkout; use `python3 bin/token-saver` to try them before
a release is published.

## Processors

Each processor handles a family of commands. The first one that matches
(`can_handle()`) processes the output. Detailed documentation for each
processor is in [`docs/processors/`](docs/processors/).

| # | Processor | Priority | Commands | Docs |
|---|---|---|---|---|
| 1 | **Package List** | 15 | pip list/freeze, npm ls, conda list, gem list, brew list | [package_list.md](docs/processors/package_list.md) |
| 2 | **just** | 18 | just --list, just --summary (recipe listing compaction) | [just.md](docs/processors/just.md) |
| 3 | **act** | 19 | act (run GitHub Actions locally via nektos/act) | [act.md](docs/processors/act.md) |
| 4 | **Git** | 20 | status, diff, log, show, push/pull/fetch, branch, stash, reflog, blame, cherry-pick, rebase, merge | [git.md](docs/processors/git.md) |
| 5 | **Test** | 21 | pytest, jest, vitest, mocha, cargo test, go test, rspec, phpunit, bun test, npm/yarn/pnpm test, dotnet test, swift test, mix test | [test_output.md](docs/processors/test_output.md) |
| 6 | **Cargo** | 22 | cargo build, check, doc, update, bench | [cargo.md](docs/processors/cargo.md) |
| 7 | **Go** | 23 | go build, vet, mod, generate, install | [go.md](docs/processors/go.md) |
| 8 | **Python Install** | 24 | pip install, poetry install/update/add, uv pip install, uv sync | [python_install.md](docs/processors/python_install.md) |
| 9 | **Build** | 25 | npm/yarn/pnpm build/install, cargo build, make, cmake, tsc, webpack, vite, next build, turbo, nx, bazel, sbt, mix compile, docker build | [build_output.md](docs/processors/build_output.md) |
| 10 | **Cargo Clippy** | 26 | cargo clippy (multi-line block grouping with span/help preservation) | [cargo_clippy.md](docs/processors/cargo_clippy.md) |
| 11 | **Lint** | 27 | eslint, ruff, flake8, pylint, clippy, mypy, prettier, biome, shellcheck, hadolint, rubocop, golangci-lint | [lint_output.md](docs/processors/lint_output.md) |
| 12 | **Maven/Gradle** | 28 | mvn, ./mvnw, gradle, ./gradlew (download stripping, task noise removal) | [maven_gradle.md](docs/processors/maven_gradle.md) |
| 13 | **Bun** | 29 | bun install, add, remove, update | [bun.md](docs/processors/bun.md) |
| 14 | **Network** | 30 | curl, wget, http/https (httpie) | [network.md](docs/processors/network.md) |
| 15 | **Docker** | 31 | ps, images, logs, pull/push, inspect, stats, compose up/down/build/ps/logs | [docker.md](docs/processors/docker.md) |
| 16 | **Kubernetes** | 32 | kubectl/oc get, describe, logs, top, apply, delete, create | [kubectl.md](docs/processors/kubectl.md) |
| 17 | **Terraform** | 33 | terraform/tofu plan, apply, destroy, init, output, state list/show | [terraform.md](docs/processors/terraform.md) |
| 18 | **Environment** | 34 | env, printenv (with secret redaction) | [env.md](docs/processors/env.md) |
| 19 | **Search** | 35 | grep -r, rg, ag, fd, fdfind | [search.md](docs/processors/search.md) |
| 20 | **System Info** | 36 | du, wc, df | [system_info.md](docs/processors/system_info.md) |
| 21 | **GitHub CLI** | 37 | gh pr/issue/run list/view/diff/checks/status | [gh.md](docs/processors/gh.md) |
| 22 | **Database Query** | 38 | psql, mysql, sqlite3, pgcli, mycli, litecli | [db_query.md](docs/processors/db_query.md) |
| 23 | **Cloud CLI** | 39 | aws, gcloud, az (JSON/table/text output compression) | [cloud_cli.md](docs/processors/cloud_cli.md) |
| 24 | **Ansible** | 40 | ansible-playbook, ansible (ok/skipped counting, error preservation) | [ansible.md](docs/processors/ansible.md) |
| 25 | **Helm** | 41 | helm install/upgrade/list/template/status/history | [helm.md](docs/processors/helm.md) |
| 26 | **Syslog** | 42 | journalctl, dmesg (head/tail with error extraction) | [syslog.md](docs/processors/syslog.md) |
| 27 | **SSH/SCP** | 43 | non-interactive ssh, scp (remote command output compression) | [ssh.md](docs/processors/ssh.md) |
| 28 | **JQ/YQ** | 44 | jq, yq (large JSON/YAML output compaction) | [jq_yq.md](docs/processors/jq_yq.md) |
| 29 | **Structured Log** | 45 | stern, kubetail (JSON Lines grouping by level) | [structured_log.md](docs/processors/structured_log.md) |
| 30 | **Pulumi** | 46 | pulumi up, preview, destroy, refresh | [pulumi.md](docs/processors/pulumi.md) |
| 31 | **CDKTF** | 47 | cdktf deploy, diff, destroy, synth | [cdktf.md](docs/processors/cdktf.md) |
| 32 | **Nix** | 48 | nix build/develop/eval/run, nix-build, nix-shell | [nix.md](docs/processors/nix.md) |
| 33 | **mise** | 49 | mise install, use, upgrade (runtime version manager) | [mise.md](docs/processors/mise.md) |
| 34 | **File Listing** | 50 | ls, find, tree, exa, eza, rsync | [file_listing.md](docs/processors/file_listing.md) |
| 35 | **File Content** | 51 | cat, head, tail, bat, less, more (content-aware: code, config, log, CSV) | [file_content.md](docs/processors/file_content.md) |
| 36 | **Generic** | 999 | Any command (fallback: ANSI strip, dedup, truncation) | [generic.md](docs/processors/generic.md) |

Lower priority numbers run first. The gaps between numbers are intentional — they leave room for [custom processors](#custom-processors) to slot in ahead of, or behind, any built-in.

## Configuration

Thresholds are configurable via JSON file or environment variables. Precedence, lowest to highest:

```
built-in defaults  <  ~/.token-saver/config.json  <  ./.token-saver.json  <  TOKEN_SAVER_* env vars
```

### Configuration File

`~/.token-saver/config.json`:

```json
{
  "enabled": true,
  "min_input_length": 1,
  "min_compression_ratio": 0.0,
  "max_diff_hunk_lines": 50,
  "max_log_entries": 10,
  "max_file_lines": 100,
  "generic_truncate_threshold": 200,
  "debug": false
}
```

Values are coerced to the type of their default, and a value that can't be coerced is ignored rather than propagated — `{"max_chain_depth": "deep"}` leaves the default in place instead of reaching arithmetic code downstream.

### Environment Variables

Every key can be overridden with the `TOKEN_SAVER_` prefix:

```bash
export TOKEN_SAVER_MAX_LOG_ENTRIES=50
export TOKEN_SAVER_DEBUG=true

# Disable compression entirely (bypass mode)
export TOKEN_SAVER_ENABLED=false
```

List-valued keys take a comma-separated string: `TOKEN_SAVER_DISABLED_PROCESSORS=file_content,network`.

### Per-Project Configuration

Drop a `.token-saver.json` in your repository root to override global settings:

```json
{
  "max_diff_hunk_lines": 300,
  "generic_truncate_threshold": 1000,
  "max_log_entries": 50
}
```

Project settings are merged with global settings. Token-Saver walks up parent directories (like `.gitignore` resolution) to find the nearest `.token-saver.json`, stopping at your home directory or the filesystem root. Useful for monorepos or projects with atypical output patterns (large Terraform plans, verbose test suites, etc.).

**Security note:** project files cannot set `user_processors_dir` (loads Python
code), `disabled_processors` or `redaction_allowlist` (can weaken redaction), or
`delta_enabled`, `delta_retention_hours`, and `delta_max_runs` (control local
output retention). Set these only in global `~/.token-saver/config.json` or via
`TOKEN_SAVER_*` environment variables. A project file that sets them has those
keys dropped with a debug-log line, not coerced. Cloning a repository cannot
opt you into retaining its command output.

### Complete Parameter List

This table is generated from `src/config.py`'s `_DEFAULTS` dict — that file is the
source of truth if the two ever disagree, and
[`tests/test_readme_config_sync.py`](tests/test_readme_config_sync.py) fails CI if
they drift apart.

| Parameter | Default | Description |
|---|---|---|
| `enabled` | `true` | Master switch -- set to `false` to bypass all compression |
| `min_input_length` | `1` | Minimum threshold (characters) to attempt compression |
| `min_compression_ratio` | `0.0` | Minimum gain to apply compression (0 = apply any gain) |
| `wrap_timeout` | `300` | Wrapper timeout in seconds |
| `max_diff_hunk_lines` | `50` | Max lines per hunk in git diff |
| `max_diff_context_lines` | `3` | Context lines kept before/after each change in diffs |
| `max_log_entries` | `10` | Max entries in git log/reflog |
| `max_file_lines` | `100` | Threshold before file content compression kicks in |
| `file_keep_head` | `80` | Lines kept from the start of file (fallback strategy) |
| `file_keep_tail` | `30` | Lines kept from the end of file (fallback strategy) |
| `generic_truncate_threshold` | `200` | Generic truncation threshold |
| `generic_keep_head` | `100` | Lines kept from the start (generic) |
| `generic_keep_tail` | `50` | Lines kept from the end (generic) |
| `generic_keep_critical` | `20` | Max error/failure lines rescued from the truncated middle (0 disables) |
| `recover_critical_lines` | `20` | Max error lines the engine re-appends when a processor dropped them (0 disables) |
| `ls_compact_threshold` | `15` | Items before ls compaction |
| `find_compact_threshold` | `20` | Results before find compaction |
| `tree_compact_threshold` | `30` | Lines before tree truncation |
| `lint_example_count` | `2` | Examples shown per lint rule |
| `lint_group_threshold` | `3` | Occurrences before grouping by rule |
| `file_code_head_lines` | `15` | Import/header lines to preserve in code files |
| `file_code_body_lines` | `2` | Body lines kept per function/class definition |
| `file_log_context_lines` | `2` | Context lines around errors in log files |
| `file_csv_head_rows` | `3` | Data rows kept from start of CSV files |
| `file_csv_tail_rows` | `2` | Data rows kept from end of CSV files |
| `search_max_per_file` | `3` | Max match lines shown per file |
| `search_max_files` | `15` | Max files shown in search results |
| `kubectl_keep_head` | `5` | Lines kept from start of kubectl logs |
| `kubectl_keep_tail` | `10` | Lines kept from end of kubectl logs |
| `docker_log_keep_head` | `5` | Lines kept from start of docker logs |
| `docker_log_keep_tail` | `10` | Lines kept from end of docker logs |
| `git_branch_threshold` | `15` | Branches before compaction |
| `git_stash_threshold` | `5` | Stash entries before truncation |
| `max_traceback_lines` | `30` | Max traceback lines before truncation |
| `db_max_rows` | `20` | Max rows shown per database query result |
| `db_prune_days` | `90` | Stats retention in days |
| `chars_per_token` | `4` | Chars-per-token ratio used to estimate token counts (display only) |
| `cargo_warning_example_count` | `2` | Example warnings shown per cargo/clippy lint |
| `cargo_warning_group_threshold` | `3` | Occurrences before grouping cargo warnings |
| `jq_passthrough_threshold` | `50` | Below this many lines, jq/yq output passes through unchanged |
| `max_chain_depth` | `3` | Maximum processor chain depth (`chain_to`) |
| `max_output_bytes` | `10000000` | Hard cap on output length (chars) before compression runs (0 disables) |
| `debug` | `false` | Enable debug logging |
| `user_processors_dir` | `""` (falls back to `~/.token-saver/processors/`) | Directory for custom processors — **global config / env var only, not project config** |
| `disabled_processors` | `[]` | Processor names to disable (env: comma-separated) — **global config / env var only, not project config** |
| `redaction_allowlist` | `[]` | Env var name patterns exempt from secret redaction — **global config / env var only, not project config** |
| `delta_enabled` | `false` | Experimental repeated-run diagnostics and local output retention — **global config / env var only, not project config** |
| `delta_retention_hours` | `24` | Delta snapshot lifetime in hours, from 1 to 168 — **global config / env var only, not project config** |
| `delta_max_runs` | `100` | Maximum retained Delta snapshots across all scopes, from 1 to 1000 — **global config / env var only, not project config** |

Parameters marked **global config / env var only** cannot be set from a
project-level `.token-saver.json` — see the security note in
[Per-Project Configuration](#per-project-configuration).

## Tuning Recipes

**"I want maximum savings and I trust the precision tests."** The defaults already apply
any gain at all (`min_compression_ratio: 0.0`), so turn the truncation thresholds down:

```json
{ "generic_truncate_threshold": 80, "max_log_entries": 5, "max_diff_context_lines": 1 }
```

**"I'm doing a careful code review and want full diffs."** Loosen the diff limits in a
project-level `.token-saver.json`:

```json
{ "max_diff_hunk_lines": 1000, "max_diff_context_lines": 10 }
```

**"Terraform plans in this repo are enormous and I need all of them."**

```json
{ "generic_truncate_threshold": 2000, "max_output_bytes": 50000000 }
```

**"One processor is mangling a tool I care about."** Disable just that one — globally,
not from a project file:

```bash
export TOKEN_SAVER_DISABLED_PROCESSORS=jq_yq
```

The generic processor can't be disabled; it's the fallback that provides `clean()`.

**"Turn everything off for this session."**

```bash
export TOKEN_SAVER_ENABLED=false
```

**"Show me what's happening."**

```bash
export TOKEN_SAVER_DEBUG=true
```

## Custom Processors

You can extend Token-Saver with your own processors for commands not covered by the built-in 36.

1. Create a Python file with a class inheriting from `src.processors.base.Processor`
2. Implement `can_handle()`, `process()`, `name`, and set `priority`
3. Copy the file to `~/.token-saver/processors/`

```bash
# Example: install the ansible processor
cp examples/custom_processor/ansible_output.py ~/.token-saver/processors/
```

A minimal processor looks like this:

```python
import re

from src.processors.base import Processor


class TfsecProcessor(Processor):
    priority = 16  # a free slot: 15 is package_list, 18 is just
    hook_patterns = [r"^tfsec\b"]

    @property
    def name(self) -> str:
        return "tfsec"

    def can_handle(self, command: str) -> bool:
        return bool(re.match(r"tfsec\b", command.strip()))

    def process(self, command: str, output: str) -> str:
        keep = [ln for ln in output.splitlines() if "Result" in ln or "CRITICAL" in ln]
        return "\n".join(keep) if keep else output
```

Two details worth knowing:

- `hook_patterns` is what the PreToolUse hook matches *before any output exists*; `can_handle()` is what the engine matches *after*. They must agree, and [`tests/test_pattern_consistency.py`](tests/test_pattern_consistency.py) enforces that for every built-in processor — a command that gets wrapped but never routed is pure overhead.
- Returning `output` unchanged is a supported, first-class outcome. It signals "I looked and decided not to compress", which the engine records differently from a failed compression attempt.

User processors are auto-discovered on every invocation. A broken processor (syntax error, missing import) is skipped with a warning — it never crashes the engine.

See [`examples/custom_processor/`](examples/custom_processor/) for a complete example with documentation, and [CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to upstream one.

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

Token counts are estimated from a `chars_per_token` ratio (default 4) — they're for
comparison and trend-watching, not for reconciling an invoice.

### Maintenance

- Auto-pruning of records older than 90 days (configurable via `db_prune_days`)
- Automatic recovery on database corruption
- Thread-safe (reentrant lock on all operations)
- WAL mode for concurrent write performance

## Security & Privacy

### What leaves your machine

Nothing, in the compression path. Compression is pure local Python — regex and string
parsing, no network, no model call, no telemetry. The only outbound request Token-Saver
ever makes is an optional GitHub release check (cached 24h, 1s timeout, fails open),
which sends nothing but a standard HTTP GET.

### What gets stored

The stats database records command strings, processor names, size measurements,
and timestamps; it does not store captured output. Command strings can themselves
contain sensitive information.

Opting into [Delta](docs/delta.md) additionally stores sanitized diagnostic
snapshots, including captured output context, in a separate private local
database. Defaults are 24-hour retention and 100 snapshots; expiry is enforced
when the store is accessed. Redaction recognizes specific secret formats and
cannot detect every secret. Disable `delta_enabled` to stop new captures and run
`token-saver delta clear` to remove retained snapshots. Deletion does not promise
secure erasure from filesystem snapshots or backups.

### How the hook is hardened

- **No shell injection**: commands are passed through `shlex.quote()` when rewriting
- **Syntax-checked rewrites**: the rewritten command is validated with `sh -n -c` before it runs; an invalid rewrite falls back to the original command
- **Fail-open**: if the hook fails (Python error, missing file, timeout), the original command executes normally. A broken Token-Saver costs you savings, not a working shell.
- **Secret redaction**: the `env` processor automatically redacts values of variables matching `*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*` patterns, preventing accidental leakage into AI context windows — and a redacted result is never discarded in favor of the raw one by the compression-ratio gate
- **Untrusted project config**: processor-loading, redaction, and Delta retention settings listed as global-only above are ignored in a repo-local `.token-saver.json`
- **Signal forwarding**: the wrapper propagates SIGINT/SIGTERM to the child process
- **Exclusions**: commands with complex pipes, redirections, `sudo`, editors, `ssh`, unquoted newlines, background `&`, or shell-construct fragments (`for`, `while`, `if`, `case`) are never intercepted
- **Safe trailing pipes**: simple trailing pipes (`| head`, `| tail`, `| wc`, `| grep`, `| sort`, `| uniq`, `| cut`) are allowed
- **Chained commands**: `&&` and `;` chains are supported — each segment is validated individually, and one ineligible segment disqualifies the whole chain
- **Self-protection**: commands containing `token-saver` or `wrap.py` are not intercepted (prevents recursion)

Quote-awareness matters here: `echo "a > b"` contains a `>` inside quotes and is *not* a
redirection, while `2>&1` is a file-descriptor duplication rather than a write to a file.
Exclusion scanning uses a quote-aware tokenizer (`src/shell_syntax.py`) rather than a
naive substring search, so quoted metacharacters don't cause false exclusions — or,
worse, false inclusions.

## Performance

Measured on macOS, Python 3.12, warm filesystem cache:

| | Time |
|---|---|
| Bare `sh -c 'echo hi'` | ~5ms |
| `python3 -c pass` (interpreter startup floor) | ~99ms |
| Full `wrap.py` round-trip | ~158ms |
| Wrapper versus bare shell | ~153ms |
| Portion beyond Python startup | ~60ms |

These previously recorded timings include interpreter startup in the full
wrapper cost. The roughly 60ms remainder is not the total overhead users pay.
Measure the full round-trip on your machine: an extra 153ms is about 15% of a
one-second command, or 0.5% of a thirty-second command. Short commands can make
the overhead more noticeable than the output reduction.

`max_output_bytes` (default 10,000,000, currently counted as characters) limits
the text passed to compression after capture. It does not limit subprocess
buffering or guarantee a bound on every parser's execution time. Delta adds
parsing, comparison, and local SQLite storage; the timings above are for ordinary
compression and do not establish its overhead.

## FAQ

**Does Token-Saver send my code or output to any server?**
No. Compression is entirely local — regex and string parsing in Python's standard
library. The only network call is an optional GitHub release check, cached for 24 hours
and silently skipped offline.

**Will it hide an error from me or from the model?**
That's the failure mode the preservation tests target. Known failures route
around processors that have not opted into failure handling, and critical-line
recovery covers selected omissions. These protections are tested on a fixture
corpus; unfamiliar formats and configured truncation can still lose useful
context. Use quality contracts for your workload and inspect `--show-removed`
when evaluating a rule. Delta retains full new or changed diagnostics for its
supported formats, with details retrievable while the snapshot is retained.

**How much will I actually save?**
It depends on your command mix, output, and detail retrievals. The tables above
measure individual fixture scenarios, not complete agent sessions. Run
`token-saver stats` for recorded command-output estimates, or
`token-saver benchmark '<command>'` for one command. Delta detail retrievals add
output and are not included in the ordinary savings tracker; account for them
separately when evaluating a complete workflow.

**Does it work with the Claude API or the Claude Agent SDK directly?**
Not as a drop-in — Token-Saver ships as a Claude Code plugin and an Antigravity CLI
plugin. But the engine is importable (`from src.engine import CompressionEngine`) and
has no dependency on either platform, so wiring it into your own agent loop is a few
lines.

**Does it work on Windows?**
Yes. Windows is a supported platform, with a `token-saver.cmd` launcher, an
`%APPDATA%`-based data directory, and UTF-8 stdio forcing at every entry point.

**Does it slow down my shell?**
No — Token-Saver only runs inside your AI assistant's tool calls. Your interactive
terminal is untouched.

**What happens if Token-Saver crashes?**
The hook fails open: the original command runs, uncompressed, exactly as it would
without Token-Saver installed. Same for a Python error, a missing file, or a timeout.

**Can I use it alongside other token-reduction MCP servers?**
Yes. Token-Saver operates at the output level; caching and delegation tools operate at
the task or invocation level. See [docs/comparison.md](docs/comparison.md).

**Why not just tell the model "be brief", or pipe through `| tail -50`?**
Because the model doesn't control tool output, and `tail -50` doesn't know the error was
on line 12. Format-aware compression keeps the 12 lines that matter out of 500 — blind
truncation keeps the last 50 and hopes.

**Does it compress files Claude reads with the Read tool?**
No. Token-Saver intercepts Bash commands; reads via the native file tool don't pass
through it. It *does* handle `cat`, `head`, `tail`, and `bat` run as shell commands —
though source code files pass through unchanged by design.

**Can a repository I clone attack me through `.token-saver.json`?**
Project configuration cannot load processors through `user_processors_dir`,
change `disabled_processors` or `redaction_allowlist`, or enable or adjust Delta
retention through `delta_enabled`, `delta_retention_hours`, or `delta_max_runs`.
Those settings require global configuration or environment variables. Other
project settings still affect compression behavior; review them when needed.

**How do I turn it off temporarily?**
`export TOKEN_SAVER_ENABLED=false`, or set `{"enabled": false}` in
`~/.token-saver/config.json`.

**Is a specific processor's behavior documented anywhere?**
Yes — [`docs/processors/`](docs/processors/) has a page per processor covering what it
matches, what it keeps, what it drops, and its config knobs.

## Troubleshooting

**A command isn't being compressed.** Ask why:

```bash
token-saver explain 'the exact command'
```

The most common answers are a redirection (`>`), a `sudo`, a complex pipe, or output
that was simply too small to be worth touching.

**Compression looks wrong for one tool.** Reproduce it in isolation and see what got
removed:

```bash
token-saver benchmark 'the exact command' --show-removed
```

If it's genuinely wrong, disable that one processor
(`export TOKEN_SAVER_DISABLED_PROCESSORS=<name>`) and please
[open an issue](https://github.com/ppgranger/token-saver/issues) with the raw output.

**Stats show nothing.** Verify the plugin is actually loaded (`/plugin` in Claude Code)
and that `token-saver version` resolves. If you installed manually, confirm
`~/.local/bin` is on your `PATH`.

**I see `[token-saver] N error line(s) recovered`.** That's the safety net working: a
processor dropped lines that looked like errors and the engine put them back. Worth
reporting — the processor should have kept them itself.

**Everything is broken and I want out.**

```bash
export TOKEN_SAVER_ENABLED=false     # immediate, this session
python3 install.py --uninstall       # permanent
```

**I need to see what the hook is doing.**

```bash
export TOKEN_SAVER_DEBUG=true
python3 scripts/wrap.py --dry-run 'git status'
```

## Known Limitations

- Does not compress commands with complex pipelines, redirections (`> file`), or `||` chains
- Simple trailing pipes are supported (`| head`, `| tail`, `| wc`, `| grep`, `| sort`, `| uniq`, `| cut`)
- Chained commands (`&&`, `;`) are supported — each segment is validated individually
- `sudo`, `ssh`, `vim` commands are never intercepted; remote `rsync` (with host:path) is excluded but local `rsync` is compressible
- Long diff compression truncates per-hunk, not per-file: a diff with many small hunks is not reduced
- The generic processor only deduplicates **consecutive identical lines**, not similar lines
- Token counts in stats are estimated from a chars-per-token ratio, not a real tokenizer
- Experimental Delta covers supported single pytest/Ruff commands in Claude Code; it needs an explicit host session and an unchanged command to compare runs
- Delta retains local output when enabled; fresh diagnostics and detail retrieval can outweigh repeated-run savings
- Antigravity CLI: the deny/reason mechanism may have side effects if other plugins use the same hook

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
│   ├── hook_session.py              # SessionStart hook wrapper
│   └── audit_compression.py         # Compression ratio corpus + report
├── antigravity/                     # Antigravity CLI specific files
│   ├── antigravity-plugin.json      # Antigravity plugin metadata
│   ├── hooks.json                   # Antigravity hook definitions
│   └── hook_aftertool.py            # AfterTool hook (Antigravity CLI)
├── bin/                             # CLI executables
│   ├── token-saver                  # Unix CLI wrapper
│   └── token-saver.cmd              # Windows CLI wrapper
├── src/                             # Shared source code
│   ├── __init__.py                  # Version (__version__) + data_dir()
│   ├── chain_utils.py               # Chained command splitting (&&, ;)
│   ├── cli.py                       # CLI entry point (version/stats/benchmark/explain)
│   ├── config.py                    # Configuration system + project trust boundary
│   ├── console.py                   # UTF-8 stdio forcing
│   ├── engine.py                    # Compression engine (orchestrator)
│   ├── diagnostics.py               # Immutable processor diagnostic contract
│   ├── delta.py                     # Compare and render completed runs
│   ├── delta_redaction.py           # Recognized secret masking for snapshots
│   ├── delta_store.py               # Private, bounded snapshot persistence
│   ├── delta_cli.py                 # Retrieve details and clear snapshots
│   ├── hook_session.py              # SessionStart hook (stats + update notif)
│   ├── platforms.py                 # Platform detection + I/O abstraction
│   ├── shell_syntax.py              # Quote-aware shell scanning (exclusions)
│   ├── stats.py                     # Stats display
│   ├── tracker.py                   # SQLite tracking
│   ├── version_check.py             # GitHub update check
│   └── processors/                  # 36 auto-discovered processors
│       ├── __init__.py
│       ├── base.py                  # Abstract Processor class
│       ├── critical.py              # Shared "is this line an error?" predicate
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
│   ├── comparison.md                # Token-Saver vs. adjacent tools
│   └── processors/                  # Per-processor documentation
├── examples/
│   └── custom_processor/            # Worked example of a user processor
├── installers/                      # Modular installer package
│   ├── common.py                    # Shared constants + utilities
│   ├── claude.py                    # Claude Code installer (native plugin registration)
│   └── antigravity.py               # Antigravity CLI installer
├── install.py                       # Installer entry point
├── CLAUDE.md                        # Plugin instructions
├── tests/
│   ├── test_engine.py               # Engine + registry tests
│   ├── test_processors.py           # Per-processor tests (the largest file by far)
│   ├── test_hooks.py                # Hook pattern + integration tests
│   ├── test_precision.py            # Precision preservation tests
│   ├── test_pattern_consistency.py  # hook_patterns vs. can_handle() agreement, per processor
│   ├── test_core.py                 # Shared compression core tests
│   ├── test_tracker.py              # SQLite + concurrency tests
│   ├── test_config.py               # Configuration tests
│   ├── test_console.py              # UTF-8 stdio forcing tests
│   ├── test_readme_config_sync.py   # README parameter table vs. _DEFAULTS drift guard
│   ├── test_version_check.py        # Version check + fail-open tests
│   ├── test_version_consistency.py  # Manifest/marketplace version drift guard
│   ├── test_cli.py                  # CLI subcommand tests
│   ├── test_user_processors.py      # Custom processor loading tests
│   ├── test_installers.py           # Installer utility tests
│   ├── test_install_smoke.py        # End-to-end installer smoke tests
│   ├── failure_fixtures.py          # One failing-command fixture per processor
│   ├── compression_baselines.json   # Recorded ratios guarded by the ratchet test
│   └── test_compression_ratchet.py  # Fails if any scenario compresses worse
├── pyproject.toml                   # Python project config + Ruff rules
├── CONTRIBUTING.md                  # Developer guide
├── LICENSE                          # Apache 2.0
└── README.md
```

## Tests

```bash
python3 -m pytest tests/ -v
```

1,300+ tests (run `python3 -m pytest tests/ --collect-only -q | tail -1` for the exact, current count) covering:

- **test_engine.py**: compression thresholds, processor priority, ANSI cleanup, generic fallback, hook pattern coverage across all supported commands
- **test_processors.py**: each processor with nominal and edge cases, chained command routing, all subcommands (blame, inspect, stats, compose, apply/delete, init/output/state, fd, exa, httpie, dotnet/swift/mix test, shellcheck/hadolint/biome, traceback truncation, ansible, helm, syslog, parameterized tests, coverage, docker compose logs, tsc typecheck, .env redaction, minified files, search directory grouping, git lockfiles/stat grouping)
- **test_hooks.py**: matching patterns for all supported commands, exclusions (pipes, sudo, editors, redirections, remote rsync, backgrounded `&`, unquoted newlines, shell-construct fragments), subprocess integration, global options (git, docker, kubectl), chained commands (shared shell state, `&&` short-circuit, `;` continue, unterminated-segment markers), safe trailing pipes
- **test_precision.py**: verification that every critical piece of data survives compression (filenames, hashes, error messages, stack traces, line numbers, rule IDs, diff changes, warning types, secret redaction under every fallback path, unhealthy pods, terraform changes, unmet dependencies) — includes `TestFailureHandling`, which runs a realistic failing-command fixture through every processor and asserts the failure reason is never lost, for every processor, at every exit code
- **test_compression_ratchet.py**: locks each real-world scenario's compression ratio, processor routing, and was-compressed status to a recorded baseline — a silent regression fails CI, not just a code review
- **test_pattern_consistency.py**: every processor's `hook_patterns` (used by the PreToolUse hook, before any output exists) must agree with its `can_handle()` (used by the engine, after output exists) — otherwise a command gets wrapped but never actually routed
- **test_readme_config_sync.py**: parses this README's parameter table and cross-checks every row against `src.config._DEFAULTS` — documentation drift fails CI instead of shipping
- **test_core.py**: shared compression core (decision, pass-through-on-error, audit logging) and the platform hook end-to-end
- **test_tracker.py**: CRUD, concurrency, corruption recovery, session tracking, stats CLI
- **test_config.py**: defaults, env overrides, invalid values, project-config trust boundaries
- **test_version_check.py**: version parsing, comparison, fail-open on errors
- **test_cli.py**: version/stats/help/explain subcommands, bin script execution
- **test_user_processors.py**: custom processor discovery and loading from `~/.token-saver/processors/`
- **test_installers.py** / **test_install_smoke.py**: version stamping, legacy migration, CLI install/uninstall, end-to-end install smoke tests

Lint and type checks match CI:

```bash
ruff check .
ruff format --check .
mypy src/ scripts/ --ignore-missing-imports
```

## Debugging

To diagnose issues:

```bash
# Test compression on a command without replacing the output
python3 scripts/wrap.py --dry-run 'git status'

# Explain routing / exclusion decisions
token-saver explain 'git status'

# See exactly what compression removed
token-saver benchmark 'git diff' --show-removed

# Enable debug logging
export TOKEN_SAVER_DEBUG=true

# Check stats
token-saver stats

# Check version
token-saver version
```

## Contributing

Contributions are welcome — especially new processors for tools that aren't covered yet.
Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, then:

1. Add your processor to `src/processors/`
2. Add tests to `tests/test_processors.py` and a failing fixture to `tests/failure_fixtures.py`
3. Add a scenario to `scripts/audit_compression.py` so the ratchet guards your ratio
4. Document it in `docs/processors/` and add a row to the [Processors](#processors) table
5. Run `ruff check . && mypy src/ scripts/ --ignore-missing-imports && python3 -m pytest tests/`

## License

Apache 2.0 — see [LICENSE](LICENSE).
