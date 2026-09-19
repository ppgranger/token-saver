---
title: Bun
description: Compress Bun package installation output, retaining package changes, summaries, and recognized warnings and errors.
permalink: /processors/bun/
parent: Processors
---

# Bun Processor

**File:** `src/processors/bun.py` | **Priority:** 29 | **Name:** `bun`

Compress Bun package installation output, retaining package changes, summaries, and recognized warnings and errors.

## Supported commands

`bun install`, `bun i`, `bun add`, `bun remove`, `bun rm`, and `bun update`.

## What it keeps

Keeps recognized errors and warnings, package-count summaries, and the first 10 recognized package-change lines. Additional changes are counted.

## What it drops or summarizes

Counts recognized resolving and downloading steps. When recognized results are present, other unrecognized lines are not included. Output with 10 lines or fewer passes through unchanged.

## Example

**Input:** 12 `Resolving dependencies` lines, then `+ example-package@1.0.0` and `1 package installed`.

**Processor output:**

```text
1 package changes:
  + example-package@1.0.0
[12 resolve/download steps]
1 package installed
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
