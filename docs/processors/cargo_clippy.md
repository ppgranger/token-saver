# Cargo Clippy Processor

**File:** `src/processors/cargo_clippy.py` | **Priority:** 26 | **Name:** `cargo_clippy`

Dedicated processor for Rust clippy lint output with multi-line block awareness.

## Supported Commands

cargo clippy (with any flags like `--all-targets`, `-- -W clippy::all`).

## Strategy

Parses clippy's multi-line warning blocks (header + `-->` span + code + `= help:` annotations) as coherent units. Groups warnings by clippy lint rule. Shows N example blocks per rule with full context. Preserves all errors in full.

| Output Type | Strategy |
|---|---|
| **Warnings** | Group by lint rule (e.g., `clippy::needless_return`). Show count + N example blocks per rule. Categorize as style/correctness/complexity/perf |
| **Errors** | Keep all error blocks in full with spans and context |
| **Checking/Compiling** | Collapse into count (e.g., `[12 checked, 3 compiled]`) |
| **Summary** | Keep `warning: X generated N warnings` summary line |

## Key Difference from Lint Processor

The generic `LintOutputProcessor` groups violations as single lines. Clippy output has multi-line blocks with `-->` spans, code snippets, and `= help:` annotations that need to be preserved as coherent units. This processor keeps the block structure intact.

## Configuration

| Parameter | Default | Description |
|---|---|---|
| cargo_warning_example_count | 2 | Number of example warning blocks to show per rule |
| cargo_warning_group_threshold | 3 | Minimum occurrences before warnings are grouped |

## Chaining

After clippy-specific processing, output is chained to the `lint` processor (`chain_to = ["lint"]`). This allows any non-clippy-specific warnings in the output to be grouped by the generic lint rule parser.

## Fallback

If this processor is disabled, `cargo clippy` falls back to the `LintOutputProcessor` which handles it at a line-by-line level.
