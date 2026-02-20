# Package List Processor

**File:** `src/processors/package_list.py` | **Priority:** 15 | **Name:** `package_list`

Handles package listing commands. Runs at high priority (15) to intercept `pip list`/`npm ls` before the build processor.

## Supported Commands

pip list, pip freeze, pip3 list, pip3 freeze, npm ls, npm list, yarn list, pnpm list, conda list, gem list, brew list.

## Strategy

- Shows total count + first 15 entries + `... (N more)`
- `npm ls` / `yarn list` / `pnpm list`: collapses dependency tree, shows top-level only, preserves UNMET DEPENDENCY and WARN/ERR warnings
- `pip list`: strips header separator lines
- `pip freeze`: simple list truncation
- `conda list`: strips comment lines
- Short outputs (< 20 entries) pass through unchanged
