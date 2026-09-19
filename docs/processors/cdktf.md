---
title: CDKTF
description: Compress CDK for Terraform output using the Terraform plan and apply processor after filtering synthesis and compilation progress.
permalink: /processors/cdktf/
parent: Processors
---

# CDKTF Processor

**File:** `src/processors/cdktf.py` | **Priority:** 47 | **Name:** `cdktf`

Compress CDK for Terraform output using the Terraform plan and apply processor after filtering synthesis and compilation progress.

## Supported commands

`cdktf deploy`, `cdktf diff`, `cdktf destroy`, `cdktf synth`, and `cdktf plan`.

## What it keeps

Delegates the Terraform-style body to the [Terraform processor](terraform.md), retaining the resource changes, summaries, and diagnostics that its plan/apply rules recognize.

## What it drops or summarizes

Filters recognized synthesis and compilation progress before processing the plan. If the remaining output has 30 lines or fewer, the original output is returned. Terraform processor limits apply to longer output.

## Example

**Input:** `Synthesizing application`, 31 `Refreshing state...` lines, then `Plan: 1 to add, 0 to change, 0 to destroy.`.

**Processor output:**

```text
Plan: 1 to add, 0 to change, 0 to destroy.
```

## Configuration and failure handling

This processor has no dedicated configuration keys. Global engine thresholds
still apply. It handles non-zero exits and has a representative failure fixture
in the [precision tests](https://github.com/ppgranger/token-saver/blob/main/tests/failure_fixtures.py).
These fixtures cover known output shapes, not every possible tool version.

See the [FAQ](../faq.md) for error-preservation limits, or return to the
[processor reference](index.md).
