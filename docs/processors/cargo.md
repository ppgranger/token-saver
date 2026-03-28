# Cargo Processor

**File:** `src/processors/cargo.py` | **Priority:** 22 | **Name:** `cargo`

Dedicated processor for Rust's cargo build system.

## Supported Commands

cargo build, cargo check, cargo doc, cargo update, cargo bench.

## Strategy

| Subcommand | Strategy |
|---|---|
| **build/check** | Collapse `Compiling X v1.0` lines into count. Group warnings by type (unused_variable, unused_import, dead_code, unused_mut, lifetime, borrow_checker). Show first N examples per type. Keep ALL errors with full span context (`-->`, `|`, `^^` markers). Keep `Finished` summary |
| **doc** | Collapse `Documenting X` and `Compiling X` lines. Keep doc warnings, errors, `Finished`, and `Generated` lines |
| **update** | Show all major version bumps explicitly (breaking changes). Collapse minor/patch bumps into count. Keep `Adding` and `Removing` lines |
| **bench** | Keep benchmark result lines (`bench: N ns/iter`). Strip `Compiling` and `Running` noise. Keep `test result:` summary |

## Exclusions

- `cargo test` is routed to `TestOutputProcessor`
- `cargo clippy` is routed to `LintOutputProcessor`

## Configuration

| Parameter | Default | Description |
|---|---|---|
| cargo_warning_example_count | 2 | Number of example warnings to show per category |
| cargo_warning_group_threshold | 3 | Minimum occurrences before warnings are grouped |

## Removed Noise

`Compiling X v1.0.0` lines, `Downloading X v1.0.0` lines, `Running` lines (bench), intermediate blank lines between warnings.
