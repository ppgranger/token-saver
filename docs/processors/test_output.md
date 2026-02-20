# Test Output Processor

**File:** `src/processors/test_output.py` | **Priority:** 21 | **Name:** `test`

Handles test runner output across all major ecosystems.

## Supported Commands

pytest, python -m pytest, jest, vitest, mocha, cargo test, go test, rspec, phpunit, bun test, npm/yarn/pnpm test, dotnet test, swift test, mix test.

## Strategy

- **Passing tests**: collapsed into `[N tests passed]`
- **Failing tests**: full stack trace and error messages **preserved**
- **Long tracebacks**: truncated to 30 lines (head + tail with marker) via `max_traceback_lines`
- **Platform/rootdir/plugins lines**: removed (pytest)
- **Final summary line**: always kept
- **Test dots** (RSpec, mix test): counted as pass/fail

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `max_traceback_lines` | 30 | Max traceback lines before truncation |

## Handler Routing

| Command Pattern | Handler |
|---|---|
| `pytest`, `python -m pytest` | `_process_pytest` |
| `jest`, `vitest`, `mocha`, `npm test`, `yarn test`, `pnpm test`, `bun test` | `_process_jest` |
| `cargo test` | `_process_cargo_test` |
| `go test` | `_process_go_test` |
| `rspec` | `_process_rspec` |
| `phpunit` | `_process_phpunit` |
| `dotnet test` | `_process_dotnet_test` |
| `swift test` | `_process_swift_test` |
| `mix test` | `_process_mix_test` |

## Example

**Before (pytest):**
```
======== test session starts ========
platform darwin -- Python 3.12.0
collected 100 items
tests/test_1.py::test_func PASSED
... (97 PASSED lines)
tests/test_db.py::test_migration FAILED
======== FAILURES ========
_____ test_migration _____
    def test_migration():
        db = get_db()
>       db.migrate('v2')
E       MigrationError: column 'email' already exists
======== 1 failed, 97 passed in 12.3s ========
```

**After:**
```
[97 tests passed]
tests/test_db.py::test_migration FAILED
======== FAILURES ========
_____ test_migration _____
    def test_migration():
        db = get_db()
>       db.migrate('v2')
E       MigrationError: column 'email' already exists
======== 1 failed, 97 passed in 12.3s ========
```
