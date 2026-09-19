---
title: Token-Saver
description: Reduce CLI output tokens for AI coding assistants with 36 specialized processors. Local compression for git, pytest, Docker, Terraform, and more.
permalink: /
nav_order: 1
---

# Token-Saver: CLI output compression for AI coding assistants

**Keep the signal. Stop rereading the same failures.**

Token-Saver is a Claude Code and Antigravity CLI plugin that intercepts the
verbose terminal output your agent reads — `git diff`, `pytest`, `npm
install`, `terraform plan`, `kubectl` — and compresses it deterministically
before it reaches the model. 36 specialized processors reduce progress logs and
boilerplate, with failure fixtures and configurable quality contracts checking
important diagnostics.

**Version 3.0.0 adds [Delta](delta.md): see what changed after the last edit.**
Repeated pytest and Ruff failures can become a concise inventory; new and changed
diagnostics keep their full details, and retained details can be retrieved on
demand. Delta is experimental, opt-in, and supports selected commands through
Claude Code.

Compression runs locally with no LLM calls or output uploads. With the same
configuration, ordinary compression gives the same output for the same input.
Delta additionally compares retained session history and assigns opaque run
identifiers for retrieval. An optional GitHub
release check is the only built-in network request; compression works offline.

## Results

| Command | Raw Output | Compressed | Savings |
|---|---|---|---|
| `git diff` (5 files, 20 context lines each) | 2,270 tokens | 546 tokens | **76%** |
| `pytest` (500 tests, 2 failures) | 6,744 tokens | 307 tokens | **95%** |
| `npm install` (220 packages) | 3,843 tokens | 4 tokens | **99.9%** |
| `cargo build` (120 crates) | 934 tokens | 21 tokens | **98%** |
| `docker build` (20 steps) | 1,682 tokens | 207 tokens | **88%** |
| `curl` download (100 progress lines) | 2,122 tokens | 0 tokens | **100%** |

Token counts are estimates based on character length, not model tokenization.
These six rows are a sample. The full set of 22 measured scenarios — sorted
by ratio, with methodology and reproduction steps — is on the
[Benchmarks](benchmarks.md) page, and it's gated by CI: a code change that
makes a scenario regress beyond the recorded tolerance fails the build.

## Install

From Anthropic's official community marketplace:

```bash
/plugin marketplace add anthropics/claude-plugins-community
/plugin install token-saver@claude-community --scope project
```

Or from the self-hosted marketplace (this repo, always current — the
official mirror is a periodic snapshot):

```bash
/plugin marketplace add ppgranger/token-saver
/plugin install token-saver
```

See the [full README](https://github.com/ppgranger/token-saver#installation)
for manual installation, Antigravity CLI setup, and upgrading from v1.x.

## Documentation

- [Delta: changes between runs](delta.md) — activation, diagnostic states, retained details, and reproducible benchmarks.
- [Compression quality gates](quality-gates.md) — compress saved logs and check budgets and required diagnostics before adopting new rules.
- [Architecture](architecture.md) — extension points and responsibilities for contributors.

- [Processor reference](processors/index.md) — one page per tool family: what each of the 36 processors keeps and drops.
- [Benchmarks](benchmarks.md) — every measured scenario, methodology, and how to reproduce them.
- [How It Compares](comparison.md) — command compression and context retrieval with RTK and Context Mode.
- [FAQ](faq.md) — privacy, error preservation, platform support, and common questions.

## Why It Exists

Every CLI command an AI coding assistant runs burns tokens, and most of that
output is noise. There are three common ways to attack this: summarize with
another LLM (accurate-ish, costs a second inference call, non-deterministic),
truncate blindly (free, but loses the one stack-trace line that mattered), or
parse the format you already know. Token-Saver is the third approach,
applied to 36 command families — deterministically, in milliseconds, with no
extra inference cost.

Source, issue tracker, and the complete README:
[github.com/ppgranger/token-saver](https://github.com/ppgranger/token-saver).
