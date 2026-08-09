---
title: FAQ
description: Answers on privacy, precision guarantees, platform support, and how Token-Saver behaves when it fails.
permalink: /faq/
---

# FAQ

## Does Token-Saver send my code or output to any server?

No. Compression is entirely local — regex and string parsing in Python's
standard library. The only network call is an optional GitHub release check,
cached for 24 hours and silently skipped offline.

## Will it hide an error from me or from the model?

That's the failure mode the whole design is built around. Errors, stack
traces, and non-zero exits are preserved; a failing command routes around
processors that haven't proven they handle failure; dropped error lines are
re-appended by the engine; and a test suite runs a failing fixture through
every processor at every exit code to prove it. Truncation, when it happens,
is always explicitly marked.

## How much will I actually save?

It depends entirely on which commands your agent runs. Sessions dominated by
test runs and installs see the high end (90%+); sessions dominated by
careful `git diff` reading see 40-70%. Run `token-saver stats` after a day
of normal use for your real number, or `token-saver benchmark '<command>'`
for a specific one. See [Benchmarks](benchmarks.md) for the full measured
set.

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

The hook fails open: the original command runs, uncompressed, exactly as it
would without Token-Saver installed. Same for a Python error, a missing
file, or a timeout.

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

Not through the three keys that would matter. `user_processors_dir`
(arbitrary code execution), `disabled_processors`, and
`redaction_allowlist` are all rejected from project-level config. The rest
are numeric thresholds with no code path to abuse.

## How do I turn it off temporarily?

`export TOKEN_SAVER_ENABLED=false`, or set `{"enabled": false}` in
`~/.token-saver/config.json`.

## Is a specific processor's behavior documented anywhere?

Yes — the [processor reference](index.md#processors) has a page per
processor covering what it matches, what it keeps, what it drops, and its
config knobs.

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Does Token-Saver send my code or output to any server?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "No. Compression is entirely local, using regex and string parsing in Python's standard library. The only network call is an optional GitHub release check, cached for 24 hours and silently skipped offline."
      }
    },
    {
      "@type": "Question",
      "name": "Will it hide an error from me or from the model?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "No. Errors, stack traces, and non-zero exits are preserved by design; a failing command routes around processors that haven't proven they handle failure, and a test suite verifies this at every exit code."
      }
    },
    {
      "@type": "Question",
      "name": "How much will Token-Saver actually save?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "It depends on which commands are run. Sessions dominated by test runs and installs see 90%+ savings; sessions dominated by git diff reading see 40-70%."
      }
    },
    {
      "@type": "Question",
      "name": "Does Token-Saver work with the Claude API or Claude Agent SDK directly?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Not as a drop-in plugin, but the compression engine is importable as a Python module and has no dependency on Claude Code or Antigravity CLI."
      }
    },
    {
      "@type": "Question",
      "name": "What happens if Token-Saver crashes?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "The hook fails open: the original, uncompressed command output is returned exactly as it would be without Token-Saver installed."
      }
    }
  ]
}
</script>
