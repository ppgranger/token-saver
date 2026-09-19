---
title: FAQ
description: Answers about local compression, error preservation, token estimates, supported platforms, and Token-Saver configuration.
permalink: /faq/
nav_order: 5
---

# FAQ

## Does Token-Saver send my code or output to any server?

No. Compression is entirely local — regex and string parsing in Python's
standard library. The only network call is an optional GitHub release check,
cached for 24 hours and silently skipped offline.

## Will it hide an error from me or from the model?

Error preservation is a tested design goal, not a guarantee for every possible
output format. Known failure output falls back to the generic processor when
the selected processor does not support failures. The engine can recover
recognized error lines for those processors, subject to configured limits.
Failure-aware processors have their own preservation tests.

The test suite checks a failure fixture for every built-in processor with
exit status `0`, `1`, and unknown. Grouping and marked truncation can still
omit detail. Inspect the [processor reference](processors/index.md) for the relevant
limits, and validate representative logs before changing thresholds.

## How much will I actually save?

It depends on the commands, their output, and your configuration. Recorded
[benchmark scenarios](benchmarks.md) range from unchanged source-code output
to fully removed progress output. Run `token-saver stats` after normal use, or
`token-saver benchmark '<command>'` for a specific command. The benchmark
command executes that command.

All token counts use a character-based estimate. Output reduction does not
equal whole-session token savings or a guaranteed reduction in API charges.

## Does it work with the Claude API or the Claude Agent SDK directly?

Not as a drop-in — Token-Saver ships as a Claude Code plugin and an
Antigravity CLI plugin. But the engine is importable (`from src.engine
import CompressionEngine`) and has no dependency on either platform, so
wiring it into your own agent loop is a few lines.

## Does it work on Windows?

Yes. Windows is a supported platform, with a `token-saver.cmd` launcher, an
`%APPDATA%`-based data directory, and UTF-8 stdio forcing at every entry
point.

## Does it slow down my shell?

No — Token-Saver only runs inside your AI assistant's tool calls. Your
interactive terminal is untouched.

## What happens if Token-Saver crashes?

Eligibility checks can leave a command unwrapped when compression is unavailable.
Compression failures handled by the adapters return captured output; they must
not rerun a command that has already executed.

A command timeout is different: the wrapper stops the child process, reports
the partial output it could collect, and exits with status `124`. Configure
`wrap_timeout` for commands that legitimately need longer.

## Can I use it alongside other token-reduction MCP servers?

Yes. Token-Saver operates at the output level; caching and delegation tools
operate at the task or invocation level. See
[How Token-Saver Compares](comparison.md).

## Why not just tell the model "be brief", or pipe through `| tail -50`?

Because the model doesn't control tool output, and `tail -50` doesn't know
the error was on line 12. Format-aware compression keeps the 12 lines that
matter out of 500 — blind truncation keeps the last 50 and hopes.

## Does it compress files Claude reads with the Read tool?

No. Token-Saver intercepts Bash commands; reads via the native file tool
don't pass through it. It does handle `cat`, `head`, `tail`, and `bat` run
as shell commands — though source code files pass through unchanged by
design.

## Can a repository I clone attack me through `.token-saver.json`?

Project configuration cannot set `user_processors_dir`, `disabled_processors`,
or `redaction_allowlist`, which control trusted code and secret masking.
It also cannot enable Delta recording or change its retention limits:
`delta_enabled`, `delta_retention_hours`, and `delta_max_runs` require global
configuration or environment variables. A project may still tune ordinary
compression thresholds, so review its configuration when output matters.

## Does Token-Saver keep diagnostic output on disk?

Ordinary compression and savings tracking do not archive output. The optional
[Experimental Delta](delta.md) retains sanitized pytest and Ruff snapshots locally
when explicitly enabled. Its defaults are 24 hours and at most 100 snapshots.
Masking recognizes common secret formats but cannot identify every secret.
Use `token-saver delta clear` to remove snapshots and reset comparisons.

## How do I turn it off temporarily?

`export TOKEN_SAVER_ENABLED=false`, or set `{"enabled": false}` in
`~/.token-saver/config.json`.

## Is a specific processor's behavior documented anywhere?

Yes — the [processor reference](processors/index.md) has a page per
processor covering what it matches, what it keeps, what it drops, and its
config knobs.
