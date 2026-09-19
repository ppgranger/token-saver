---
title: Delta Between Runs
description: Compare repeated pytest and Ruff diagnostics in Claude Code, retrieve retained details, and control opt-in local snapshot storage.
permalink: /delta/
nav_order: 8
---

# See what changed after the last edit

Delta compares diagnostics from repeated command executions. New and changed
failures show their full captured details; unchanged failures keep a summary and
an identifier. The current exit status and totals remain visible, and retained
details can be retrieved without running the command again.

Delta is an **experimental, opt-in feature introduced in 3.0.0**.
The interface and supported formats may evolve.
Existing general benchmark results describe ordinary compression, not Delta.
The synthetic sequence below measures Delta output size, including optional
retrieval; improvement in agent task success has not been measured.

## Enable it explicitly

Delta is disabled by default. Add the following key to your existing global
`~/.token-saver/config.json`, or the corresponding file under
`%APPDATA%/token-saver/` on Windows:

```json
{
  "delta_enabled": true
}
```

Alternatively, set the environment variable before launching Claude Code:

```bash
export TOKEN_SAVER_DELTA_ENABLED=true
```

Only global configuration and environment variables can enable Delta or change
its retention. Project-level `.token-saver.json` files cannot set these options.
The master `enabled` switch must also be on.

Run supported commands through Claude Code as usual. The wrapper needs the
explicit `TOKEN_SAVER_SESSION` supplied by the host integration; without a
session identifier it uses ordinary compression. Comparing runs requires the
same session, working directory, exact command text, tool family, and Token-Saver
version. Changing command arguments starts a separate comparison baseline.

## Read the result

Each Delta response shows the current command's exit status, summary, and current
diagnostics. The labels mean:

| Label | Observation |
|---|---|
| `NEW` | This identifier was absent from the previous comparable snapshot. Its full current details follow. |
| `CHANGED` | The same diagnostic identifier has different summary or detail text. Its full current details follow. |
| `UNCHANGED` | The same identifier, summary, and details appeared previously. Its summary remains visible. |
| `PASSED` | A previously failing test was explicitly reported passing in this run. |
| `NOT OBSERVED` | A previous diagnostic is absent, with no explicit passing result. It is not confirmed fixed. |

On the first comparable run, all current diagnostics are `NEW`. A changed
traceback also produces full details again. **These responses can be larger than
ordinary v2 compression** when retaining full new or changed details requires it.

If ordinary sanitized compression is no larger and already includes every full
new or changed diagnostic, Token-Saver displays that result instead. With only
unchanged diagnostics, Delta is therefore displayed only when strictly shorter.
The valid snapshot is retained as a baseline in either case. Saving a baseline
does not necessarily produce a visible Delta response or retrieval identifier.

Use `pytest -v` when you want individual passing test results. A quiet summary
such as `10 passed` does not prove that a particular previously failing test ran.
Likewise, a Ruff diagnostic disappearing does not establish that a test passed:
it is reported as `NOT OBSERVED`, even if the current lint summary is successful.

Captured warnings and other surrounding text remain in each response. This can
limit savings when most output is outside the recognized diagnostics. This
preservation applies to the Delta rendering; ordinary-compression fallbacks
retain their existing configured truncation and warning-grouping behavior.

## Retrieve details without rerunning

Every displayed Delta result includes a command containing its opaque run
identifier:

```bash
token-saver delta show RUN
token-saver delta show RUN --diagnostic 'tests/test_api.py::test_login'
```

Replace `RUN` with the 32-character identifier printed by Delta. The optional
`--diagnostic` value must match the exact identifier in that snapshot. Pytest
identifiers are test node IDs; Ruff identifiers are `path:row:column:rule`.

`show` reads a complete snapshot of that run, including full details for failures
that were previously summarized as unchanged. It needs no earlier snapshot and
does not execute the original command. Status is `0` for a successful read, `1`
for a missing or expired snapshot or missing diagnostic, and `2` for invalid input
or unavailable storage. These are retrieval statuses, not the original command's
exit status.

Use `python3 bin/token-saver` instead of `token-saver` when invoking these CLI
commands directly from a source checkout.

## Supported commands and formats

Delta currently applies to **single completed commands in the Claude wrapper**.
It does not change the ordinary Antigravity, `compress`, `replay`, or `benchmark`
paths. Wrapper dry runs and stdin capture paths do not create Delta snapshots.
Commands are always executed normally; Delta does not reuse an old result in
place of an execution.

| Tool | Supported input | Conservative fallback examples |
|---|---|---|
| Pytest | Complete normal text results with matching failure sections, short-summary test IDs, and run totals; `pytest -v` exposes explicit passing results. | Collection errors, interrupted runs, missing totals, ambiguous test names, inconsistent counts, altered traceback/capture modes, collection-only and setup modes. |
| Ruff | `ruff check` full or concise text diagnostics, including current `RULE message` blocks and legacy `path:row:column: RULE message` lines, with a matching final summary. | JSON and other machine formats, fix/diff/watch modes, statistics, quiet output, redirected output files, and forced-success exit modes. |

Simple executable paths, Python module invocations, and `uv run`, `poetry run`,
or `pipx run` launchers can be recognized when they reach the wrapper. This does
not broaden the hook's existing command eligibility rules.

Delta excludes shell chains, pipes, redirections, and substitutions, including
pipes that ordinary compression may accept. It also declines unknown formats,
more than 500 diagnostics, exit statuses outside `0` and `1`, and current input
larger than **1,000,000 UTF-8 bytes**. Uncertain parsing or unavailable storage
returns ordinary compression, retaining any redaction already applied. The
wrapper still returns the command's actual exit status.

If an ordinary processor has already masked secrets, Delta keeps that result
and does not capture a snapshot from the original output. This preserves custom
masking rules that Delta's own recognizers cannot know about.

## Reproduce the output-size benchmark

Run from the source checkout:

```bash
python3 examples/delta_benchmark.py
```

The standalone example feeds five **synthetic pytest captures** through the
current compressor and Delta: baseline, repeat, edit, repeat, repeat. Each run
has 34 tests and three verbose list-comparison failures. The edit fixes one
test, changes another failure, and introduces a new failure. The example uses
default settings and a disposable home and snapshot database; it neither runs
pytest nor reads your normal configuration. Retrieval uses the actual `show`
implementation against the final retained snapshot.

Measured output with this source version:

| Five-run scenario | Output characters | Estimated tokens | Reduction versus ordinary compression |
|---|---:|---:|---:|
| Ordinary compression | 13,639 | ~3,411 | — |
| Delta, without retrieval | 6,942 | ~1,737 | 49.1% |
| Delta plus one diagnostic retrieval | 7,906 | ~1,978 | 42.0% |
| Delta plus one complete snapshot retrieval | 10,148 | ~2,539 | 25.6% |

The retrieval rows are separate alternatives, each including one additional
response. Estimated tokens are calculated as `ceil(characters / 4)` separately
for each response, then summed, using the default four-character ratio. They
are not measured model usage or billing savings. Counts include Delta's
retrieval hints, but exclude the agent's request and tool-call overhead.

This deliberately narrow fixture measures repeated verbose failures. The first
Delta response is larger than ordinary compression because it retains full new
details. Short diagnostics may produce no savings and use ordinary compression;
more frequent or larger retrievals can erase the gain. These results do not
measure agent task completion, accuracy, or elapsed time.

## Run the real-command benchmark

With the repository's pytest and Ruff development dependencies installed:

```bash
python3 examples/delta_live_benchmark.py
python3 examples/delta_live_benchmark.py --json
```

This benchmark executes real tools through the actual wrapper on generated,
disposable projects. Both ordinary compression and Delta run the same five
stages: baseline, repeat, edit, repeat edited, and passing. The pytest fixture
has 24 tests with verbose list-comparison failures; the Ruff fixture has three
undefined-name diagnostics. Profiles, configuration, and retained data are
isolated from your normal installation.

It checks original exit statuses, new and changed diagnostic evidence, successful
final results, and retrieval. The pytest fixture counts collections to verify
that every requested execution happens and reading details does not rerun it.
The two retrieval rows are alternatives, each adding one read from the first
repeated result. Totals include output on stdout/stderr and retrieval hints;
requests and tool-call overhead are excluded.

Measured with **Python 3.14.7, pytest 9.0.2, and Ruff 0.15.15**:

| Complete five-run sequence | Pytest characters | Change vs ordinary | Ruff characters | Change vs ordinary |
|---|---:|---:|---:|---:|
| Ordinary compression | 16,458 | — | 2,219 | — |
| Delta | 9,529 | 42.1% less | 1,852 | 16.5% less |
| Delta + one targeted read | 11,106 | 32.5% less | 2,034 | 8.3% less |
| Delta + one complete read | 14,520 | 11.8% less | 2,654 | **19.6% more** |

For pytest, ordinary/Delta counts by stage are **4,079/5,075**, **4,079/374**,
**4,091/3,584**, **4,091/378**, and **118/118**. This shows both the initial cost
of preserving complete details and the benefit of repeating them compactly.
The two repeated stages alone save 90.8% for pytest and 33.4% for Ruff; those
figures exclude the other stages and must not replace the complete totals.

Verified copies of pytest's multiline exception summary are omitted only when
the same complete exception block is already retained verbatim in the primary
traceback. Unique details, warnings, and unrecognized continuations remain.
The benchmark uncovered this duplication and uses the same fixture before and
after the correction.

The report also estimates tokens by summing `ceil(characters / 4)` separately
for every response. Timings embedded in tool output and different tool versions
can change character counts. These are real command executions on controlled
fixtures, not real-world agent sessions, measured billing, or proof of improved
task completion.

## Local storage and retention

Enabling Delta allows **sanitized output snapshots to be written to disk**.
Snapshots include diagnostic details and surrounding captured context. They use
a separate SQLite database, `delta/snapshots.sqlite3`, below
`TOKEN_SAVER_DB_DIR` when set, or the normal platform data directory otherwise:
`~/.token-saver/` on Unix and `%APPDATA%/token-saver/` on Windows.

| Setting | Default | Accepted values |
|---|---|---|
| `delta_enabled` | `false` | Boolean; global configuration or environment only. |
| `delta_retention_hours` | `24` | Integer from 1 to 168; global configuration or environment only. |
| `delta_max_runs` | `100` | Integer from 1 to 1000 across all sessions and scopes; global configuration or environment only. |

For example, `TOKEN_SAVER_DELTA_RETENTION_HOURS=8` lowers the lifetime to eight
hours. Each encoded snapshot has a **1 MiB (1,048,576-byte)** limit. These are
snapshot content and record-count limits, not an exact disk-size quota.

Expiry and count limits are enforced when the store is opened or accessed;
there is no background deletion job. Expired snapshots cannot be retrieved.
If the system clock moves backward, snapshots now dated in the future are
discarded on access. The newest inserted results take priority under the count
limit, even when timestamps coincide.
Directories and files use private POSIX permissions, with Windows access also
depending on the containing directory's ACL. Data paths reject symlinks and
nonregular files. Corrupt storage is reported to the optional integration and
is not silently wiped and recreated.

Comparison metadata is hashed before storage; run identifiers do not embed
commands, paths, or session IDs. Captured output can still contain paths or other
sensitive information. The existing savings database is unchanged and continues
to record command metadata and size measurements separately.

Delta applies deterministic secret masking before parsing, comparing, or
storing a snapshot, and again when showing it. It recognizes specific credential
assignments, authorization headers, URL passwords, token formats, and private
keys. **This is not universal secret detection:** unfamiliar secrets and formats
can remain in captured output.

To stop recording and remove retained history:

```bash
export TOKEN_SAVER_DELTA_ENABLED=false
token-saver delta clear
```

Update global configuration or the environment inherited by Claude accordingly.
Disabling Delta alone does not delete existing snapshots. `clear` removes all
retained snapshots and resets comparison baselines; the next eligible execution
starts a new baseline. Deletion does not promise secure erasure from filesystem
snapshots, backups, or other copies.
