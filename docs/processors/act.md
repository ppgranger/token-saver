---
title: Act
description: Compress local GitHub Actions logs from act while retaining workflow output, step results, job status, and recognized errors.
permalink: /processors/act/
parent: Processors
---

# Act Processor

**File:** `src/processors/act.py` | **Priority:** 19 | **Name:** `act`

Compress local GitHub Actions logs from act while retaining workflow output, step results, job status, and recognized errors.

## Supported commands

`act` commands that run GitHub Actions locally.

## What it keeps

Keeps step markers, success and failure results, job status, recognized error lines, and lines beginning with `|` that contain workflow output. Other nonempty lines are retained unless they match Docker or setup noise.

## What it drops or summarizes

Collapses recognized container setup, pull, copy, cleanup, and preparation lines into a count. Output with 15 lines or fewer passes through unchanged.

## Example

**Input:** 16 `docker pull build-image` lines followed by `Job failed: test suite failed`.

**Processor output:**

```text
Job failed: test suite failed
[16 docker/setup lines hidden]
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
