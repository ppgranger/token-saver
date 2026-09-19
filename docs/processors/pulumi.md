---
title: Pulumi
description: Compact Pulumi infrastructure updates and previews while retaining resource operations, output summaries, and recognized diagnostics.
permalink: /processors/pulumi/
parent: Processors
---

# Pulumi Processor

**File:** `src/processors/pulumi.py` | **Priority:** 46 | **Name:** `pulumi`

Compact Pulumi infrastructure updates and previews while retaining resource operations, output summaries, and recognized diagnostics.

## Supported commands

`pulumi up`, `pulumi update`, `pulumi preview`, `pulumi destroy`, and `pulumi refresh`.

## What it keeps

Keeps resource-operation lines marked with `+`, `-`, or `~`, recognized errors and warnings, and continuation lines in error blocks. Also keeps Resources, Outputs, and Diagnostics headers with their indented details, plus duration and operation headers.

## What it drops or summarizes

Replaces other nonempty progress lines with a hidden-line count. Output with 20 lines or fewer passes through unchanged.

## Example

**Input:** 21 `Checking resource status` lines, then `+ aws:s3/bucket:Bucket logs`, `Resources:`, and an indented `+ 1 to create`.

**Processor output:**

```text
+ aws:s3/bucket:Bucket logs
Resources:
    + 1 to create
[21 unchanged/progress lines hidden]
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
