---
title: Just
description: Compact long just recipe listings with recipe counts, an explicit overflow marker, and recognized errors.
permalink: /processors/just/
parent: Processors
---

# Just Processor

**File:** `src/processors/just.py` | **Priority:** 18 | **Name:** `just`

Compact long just recipe listings with recipe counts, an explicit overflow marker, and recognized errors.

## Supported commands

`just --list`, `just -l`, and `just --summary` listings. Recipe execution such as `just build` is not handled by this processor.

## What it keeps

Keeps non-recipe lines and recognized errors, counts indented recipe entries, and shows the first 40 entries.

## What it drops or summarizes

Removes blank lines and replaces recipes beyond the first 40 with an explicit omitted count. Output with 30 lines or fewer, or no recognized indented recipes, passes through unchanged.

## Example

**Input:** `just --summary` returns a single line: `build test deploy`.

**Processor output:**

```text
build test deploy
```

A compact summary passes through unchanged; this processor targets long,
indented recipe listings.

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
