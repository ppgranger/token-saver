---
title: Token-Saver
description: Content-aware output compression for AI coding assistants. 36 specialized processors cut CLI output tokens by 60-99% without losing errors, diffs, or stack traces.
permalink: /
---

# Token-Saver

**Content-aware output compression for AI coding assistants.**

Token-Saver is a Claude Code and Antigravity CLI plugin that intercepts the
verbose terminal output your agent reads — `git diff`, `pytest`, `npm
install`, `terraform plan`, `kubectl` — and compresses it deterministically
before it reaches the model. 36 specialized processors understand the shape
of each tool's output, so errors, diffs, and stack traces survive while
progress bars, passing tests, and installation logs are dropped.

No LLM calls. No network access. Fully offline and deterministic — the same
input always produces the same output.

## Results

| Command | Raw Output | Compressed | Savings |
|---|---|---|---|
| `git diff` (5 files, 20 context lines each) | 2,270 tokens | 546 tokens | **76%** |
| `pytest` (500 tests, 2 failures) | 6,744 tokens | 307 tokens | **95%** |
| `npm install` (220 packages) | 3,843 tokens | 4 tokens | **99.9%** |
| `cargo build` (120 crates) | 934 tokens | 21 tokens | **98%** |
| `docker build` (20 steps) | 1,682 tokens | 207 tokens | **88%** |
| `curl` download (100 progress lines) | 2,122 tokens | 0 tokens | **100%** |

These six rows are a sample. The full set of 22 measured scenarios — sorted
by ratio, with methodology and reproduction steps — is on the
[Benchmarks](benchmarks.md) page, and it's gated by CI: a code change that
makes any of them compress worse fails the build.

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

- [Benchmarks](benchmarks.md) — every measured scenario, methodology, and how to reproduce them.
- [How It Compares](comparison.md) — vs `cc_token_saver_mcp`, `token-optimizer-mcp`, and Claude Context Mode.
- [FAQ](faq.md) — privacy, precision guarantees, platform support, and common questions.
- [Processor reference](#processors) — what each of the 36 processors keeps and drops.

## Processors

One page per tool family, documenting exactly what's kept, what's dropped,
and which config knobs are available:

<ul>
{% assign processors = site.pages | where_exp: "p", "p.permalink contains '/processors/'" | sort: "title" %}
{% for p in processors %}
  <li><a href="{{ p.url | relative_url }}">{{ p.title }}</a> — {{ p.description }}</li>
{% endfor %}
</ul>

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
