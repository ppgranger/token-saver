# Lint Output Processor

**File:** `src/processors/lint_output.py` | **Priority:** 27 | **Name:** `lint`

Handles linter and static analysis output.

## Supported Commands

eslint, ruff, flake8, pylint, clippy (cargo clippy), rubocop, golangci-lint, stylelint, prettier --check, biome check/lint, mypy, shellcheck, hadolint, tflint, ktlint, swiftlint.

## Strategy

- Groups violations by rule ID: `no-var: 15 occurrences in 8 files`
- Shows 2 examples per rule (configurable), collapses the rest
- Summary: `20 issues across 2 rules:`
- Keeps summary/total lines and important ungrouped lines (fatal errors)

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `lint_example_count` | 2 | Examples shown per lint rule |
| `lint_group_threshold` | 3 | Occurrences before grouping by rule |

## Supported Formats

| Linter | Format Detected |
|---|---|
| ESLint (block) | File header + indented `line:col error message rule` |
| ESLint (inline) | `file:line:col: message (rule)` |
| Ruff/Flake8 | `file:line:col: E501 message` |
| Pylint | `file:line:col: C0114: message (rule-name)` |
| mypy | `file:line: error: message [error-code]` |
| Clippy | `warning[rule]: message` or `warning: message [rule-name]` |
| shellcheck | `file:line:col: level - SC2086 message` |
| hadolint | `file:line DL3008 message` |
| biome | `file:line:col lint/rule message` |

## Example

**Before:**
```
src/file0.ts
  10:0  error  Unexpected var  no-var
  20:0  error  Missing return  consistent-return
src/file1.ts
  10:1  error  Unexpected var  no-var
  20:1  error  Missing return  consistent-return
... (8 more identical files)
20 problems (20 errors, 0 warnings)
```

**After:**
```
20 issues across 2 rules:
  no-var: 10 occurrences in 10 files
    10:0  error  Unexpected var  no-var
    10:1  error  Unexpected var  no-var
    ... (8 more)
  consistent-return: 10 occurrences in 10 files
    20:0  error  Missing return  consistent-return
    20:1  error  Missing return  consistent-return
    ... (8 more)
20 problems (20 errors, 0 warnings)
```
