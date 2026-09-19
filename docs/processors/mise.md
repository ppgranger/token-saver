---
title: Mise
description: Reduce mise runtime installation progress while preserving installation results and recognized warnings and errors.
permalink: /processors/mise/
parent: Processors
---

# Mise Processor

**File:** `src/processors/mise.py` | **Priority:** 49 | **Name:** `mise`

Reduce mise runtime installation progress while preserving installation results and recognized warnings and errors.

## Supported commands

`mise install`, `mise i`, `mise use`, `mise upgrade`, and `mise up`.

## What it keeps

Keeps recognized errors, warnings, installation lines with runtime versions, and other nonempty lines that are not recognized progress.

## What it drops or summarizes

Counts downloading, extracting, verifying, fetching, building, and compiling progress lines. Output with 10 lines or fewer passes through unchanged.

## Example

**Input:** 12 `mise downloading node` lines followed by `mise installed node@22.0.0`.

**Processor output:**

```text
mise installed node@22.0.0
[12 download/build steps]
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
