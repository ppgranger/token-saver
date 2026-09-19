---
title: Nix
description: Summarize Nix build and store-transfer output with counts while retaining recognized diagnostics and plan summaries.
permalink: /processors/nix/
parent: Processors
---

# Nix Processor

**File:** `src/processors/nix.py` | **Priority:** 48 | **Name:** `nix`

Summarize Nix build and store-transfer output with counts while retaining recognized diagnostics and plan summaries.

## Supported commands

`nix build`, `nix develop`, `nix run`, `nix eval`, `nix shell`, `nix flake` subcommands, `nix-build`, `nix-shell`, and `nix-env`.

## What it keeps

Keeps recognized plan summaries, warnings, errors, hints, and nonempty lines that do not match build or transfer noise.

## What it drops or summarizes

Counts derivation builds, copied paths, fetch operations, and standalone store paths. Individual store paths can therefore be omitted from long output. Output with 15 lines or fewer passes through unchanged.

## Example

**Input:** 16 `building '/nix/store/example.drv'` lines followed by `error: build failed`.

**Processor output:**

```text
error: build failed
[16 derivations built]
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
