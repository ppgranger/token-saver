---
title: Benchmarks
description: 22 measured compression scenarios for Token-Saver, sorted by ratio, gated by CI so they cannot regress silently.
permalink: /benchmarks/
nav_order: 3
---

# Token-Saver Compression Benchmarks

Version: **2.7.2** · Baselines last updated: **2026-08-02** · Source: [`tests/compression_baselines.json`](https://github.com/ppgranger/token-saver/blob/main/tests/compression_baselines.json)

These are not marketing estimates. Every row below is a fixed baseline
checked into the repository and enforced by
[`tests/test_compression_ratchet.py`](https://github.com/ppgranger/token-saver/blob/main/tests/test_compression_ratchet.py):
CI fails if a code change makes any scenario compress worse than its recorded
ratio (within a 2 percentage-point tolerance for incidental drift). The
numbers can only go up, or a PR has to explicitly justify why one went down.

## Methodology

1. [`scripts/audit_compression.py`](https://github.com/ppgranger/token-saver/blob/main/scripts/audit_compression.py)
   defines each scenario as a realistic `(command, output)` pair — e.g. a
   `pytest` run with 500 tests and 2 failures, built from real-world output
   shapes, not cherry-picked snippets.
2. Each scenario is run through the real `CompressionEngine`
   (`src/engine.py`), the same code path a live Claude Code or Antigravity
   CLI session uses — no mocking, no separate "demo" implementation.
3. The ratio is computed in **tokens**, not bytes or lines, using the same
   `chars_per_token` estimate the engine uses internally, so the reported
   percentage matches what actually leaves the context window.
4. Baselines are regenerated only deliberately, by re-running the audit
   script and committing the new JSON — never silently.

Reproduce any row yourself:

```bash
git clone https://github.com/ppgranger/token-saver.git && cd token-saver
python3 scripts/audit_compression.py            # full report, all scenarios
python3 scripts/audit_compression.py --json      # machine-readable ratios
python3 -m pytest tests/test_compression_ratchet.py -v
```

Or benchmark your own command instead of a fixed scenario:

```bash
python3 bin/token-saver benchmark 'git log --oneline -50'
```

## Results

| Scenario | Processor | Compression ratio | Compressed? |
|---|---|---|---|
| `curl download (100 progress lines)` | network | 100.0% | Yes |
| `npm install (220 packages)` | build | 99.9% | Yes |
| `cargo build (120 crates)` | cargo | 97.8% | Yes |
| `pytest (200 passed, 30 warnings, 0 failures)` | test | 97.7% | Yes |
| `git diff --stat (25 files)` | git | 96.0% | Yes |
| `pytest (500 passed, 2 failed)` | test | 95.4% | Yes |
| `pip install -r requirements.txt (30 packages)` | python_install | 95.1% | Yes |
| `jest (50 suites, all passing)` | test | 94.4% | Yes |
| `tree (350+ lines)` | file_listing | 92.6% | Yes |
| `eslint (55 violations, 2 rules)` | lint | 88.8% | Yes |
| `docker build (20 steps)` | build | 87.7% | Yes |
| `ruff check (110 violations, 4 rules)` | lint | 87.4% | Yes |
| `git log --oneline (50 entries, already compact)` | git | 79.4% | Yes |
| `git diff (5 files, 20 context lines each)` | git | 75.9% | Yes |
| `find . -name '*.py' (205 results)` | file_listing | 75.1% | Yes |
| `npm audit (15 vulnerabilities)` | build | 72.9% | Yes |
| `ls (126 items)` | file_listing | 57.0% | Yes |
| `mypy (30 errors, 5 rules)` | lint | 54.8% | Yes |
| `git status (30+ files, verbose format)` | git | 32.7% | Yes |
| `cat large_file.py (1000 lines)` | file_content | 0.0% | No |
| `git status -s (45 files, short format)` | git | 0.0% | No |
| `tsc (7 type errors)` | build | 0.0% | No |

## Reading the zero-percent rows

Three scenarios above show 0% deliberately, not as a bug:

- **`cat large_file.py`** — source code passes through unchanged. Token-Saver
  intercepts shell commands, not the model's own file-reading tool, and it
  will not risk truncating code the model needs verbatim.
- **`git status -s`** — the short format is already as dense as the
  information it carries; there is nothing left to remove.
- **`tsc` (7 type errors)** — a handful of type errors is already the signal,
  not the noise. Compressing it further would risk dropping an error.

Token-Saver returns the original bytes in these cases rather than shaving a
few tokens at the cost of correctness. See
[Precision Guarantees](https://github.com/ppgranger/token-saver/blob/main/README.md#precision-guarantees)
for how that's enforced across all 36 processors.

## See also

- [How Token-Saver Compares](comparison.md) — the same rigor applied to
  competing approaches (LLM summarization, blind truncation, caching).
- [Processor reference](processors/) — per-tool documentation of what each
  processor keeps and drops.
