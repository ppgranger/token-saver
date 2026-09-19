---
title: Compression Quality Gates
description: Check token budgets and required diagnostic text against captured CLI outputs, with offline replay and JSON reports for continuous integration.
permalink: /quality-gates/
nav_order: 6
---

# Compression you can verify

Choose a context budget and the exact messages your workflow needs. Token-Saver
checks both against the real compression result. A budget violation fails the
check **without truncating the output further**. This makes errors visible when
the requested budget and required information cannot both fit.

These commands are available in the source checkout containing this page. Run
`python3 bin/token-saver` in place of `token-saver` when trying unreleased changes.

## A portable stdin filter

```bash
token-saver compress 'pytest -v' --exit-code 1 --max-tokens 1500 < pytest-output.txt
```

`compress` reads captured UTF-8 output from stdin and writes compressed text to
stdout. The command string only chooses a processor: **it is never executed**.
This works in scripts and agent integrations that can pipe text, independently
of the existing automatic Claude Code and Antigravity hooks.

- `--exit-code` supplies the original command's status so failure-aware routing
  can protect unexpected diagnostics. Omit it if the status is unknown.
- `--max-tokens` checks an estimated output budget; an overrun retains the full
  compressed result, prints a diagnostic to stderr, and returns status `1`.
- `--format json` returns the compressed `output`, measurements, limits and
  check verdict in a single JSON object.

The exit status is the **filter/check status**, not the original command's status.
When composing a shell pipeline, capture or propagate upstream failures explicitly;
a successful filter alone does not prove that the upstream command succeeded.

## Replay a whole workflow offline

Keep captured outputs beside a JSON manifest:

```json
{
  "schema_version": 1,
  "max_total_tokens": 2000,
  "cases": [
    {
      "name": "failed tests keep the root cause",
      "command": "pytest -v",
      "input": "fixtures/tests.txt",
      "exit_code": 1,
      "max_tokens": 1500,
      "min_savings_percent": 20,
      "must_preserve": ["AssertionError", "tests/test_auth.py"]
    }
  ]
}
```

```bash
token-saver replay quality.json
token-saver replay quality.json --format json > quality-report.json
```

Each case can require a maximum estimated token count, a minimum percentage of
characters saved, and literal text that must appear in **both** the input fixture
and compressed output. The latter catches misspelled expectations as well as
lost diagnostics. Matching is case-sensitive substring matching, not a claim of
semantic equivalence. Add expectations for your important filenames, errors,
resource IDs or diff lines; passing them does not prove all information survived.

The optional `max_total_tokens` checks the sum of per-case estimates, useful for
the total context a workflow consumes. A total-budget failure can occur even
when every individual case passes.

The bundled example is runnable from the repository:

```bash
python3 bin/token-saver replay examples/quality-replay.json
```

## Use it in CI

```yaml
- name: Check compression budgets and diagnostic preservation
  run: python3 bin/token-saver replay examples/quality-replay.json --format json
```

| Status | Meaning |
| --- | --- |
| `0` | All configured checks pass |
| `1` | A quality or budget check fails |
| `2` | Invalid arguments, manifest, configuration value or unreadable input |

Unknown manifest fields, duplicate case names and invalid thresholds are rejected
so a typo cannot silently disable a contract. Fixtures must be regular files
inside the manifest directory, including after symbolic-link resolution. The
manifest is limited to 1 MB and 1,000 cases; each capture is bounded by the
existing `max_output_bytes` setting (10 MB by default).

## Estimates and privacy

Token counts are **estimates** calculated as `ceil(characters / chars_per_token)`
with the configured ratio, default `4`. They are not model-tokenizer counts,
provider billing measurements or a hard guarantee that text fits every model.
Savings thresholds use the unrounded character reduction.

Replay reports contain case names, processor names, measurements and failed check
indices. They do not include command strings, captured output or required text.
Choose non-sensitive case names and sanitize fixtures before committing them.
`compress --format json` intentionally includes the compressed output.
Neither command archives raw output or writes savings history.

Both use the current Token-Saver configuration and installed processors. Pin the
revision and configuration in CI for reproducibility; replay itself does not run
the command labels or contact a model. User processors remain trusted Python
extensions and execute their own compression code.

See [measured benchmarks]({{ '/benchmarks/' | relative_url }}) and the
[processor reference]({{ '/processors/' | relative_url }}) for existing behavior.
