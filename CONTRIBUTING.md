# Contributing to Token-Saver

## How to contribute

This project uses a **fork-based workflow**. Direct pushes to `main` are not
allowed — all changes go through pull requests reviewed by maintainers.

### 1. Fork and clone

```bash
# Fork the repo on GitHub (click the "Fork" button), then:
git clone https://github.com/<your-username>/token-saver.git
cd token-saver/extension
```

### 2. Create a branch

```bash
git checkout -b my-feature
```

### 3. Make your changes

Edit the code, add tests, and make sure everything passes locally:

```bash
# Lint
ruff check .
ruff format --check .

# Tests
python3 -m pytest tests/ -v
```

### 4. Commit and push

```bash
git add -A
git commit -m "Add my feature"
git push origin my-feature
```

### 5. Open a pull request

Go to your fork on GitHub and click **"New pull request"**. Target the `main`
branch of the upstream repository. Fill in the PR template.

### 6. CI and review

- A **maintainer** must approve your PR before CI runs (GitHub's
  "Require approval for first-time contributors" setting).
- CI runs **ruff check**, **ruff format --check**, and **pytest** on
  Python 3.10, 3.12, and 3.13.
- Both CI and a maintainer review must pass before merging.
- Only maintainers can merge to `main`.

### Keeping your fork up to date

```bash
git remote add upstream https://github.com/<org>/token-saver.git
git fetch upstream
git rebase upstream/main
```

---

## Code quality

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and
formatting. Configuration is in `pyproject.toml`.

```bash
# Check for lint issues
ruff check .

# Auto-fix safe issues
ruff check --fix .

# Check formatting
ruff format --check .

# Auto-format
ruff format .
```

All code must pass `ruff check` and `ruff format --check` before merging.

---

## Adding a new processor

Adding a new processor is a **single-file operation**. Create one file in
`src/processors/` and it will be automatically discovered.

### Quick start

1. Create `src/processors/my_tool.py`
2. Run `python3 -m pytest tests/ -v` to verify

That's it. No other files need editing.

### Processor template

```python
"""MyTool output processor: describe what it handles."""

import re

from .base import Processor


class MyToolProcessor(Processor):

    priority = 40          # See priority conventions below
    hook_patterns = [
        r"^mytool\s+(subcommand1|subcommand2)\b",
    ]

    @property
    def name(self) -> str:
        return "my_tool"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\bmytool\s+(subcommand1|subcommand2)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output
        # Your compression logic here
        return output
```

### Required attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `priority` | `int` | Determines processor ordering. Lower = checked first. |
| `hook_patterns` | `list[str]` | Regex patterns for the pre-tool hook to intercept matching commands. |
| `name` | `str` (property) | Identifier returned by the engine to report which processor handled a command. |
| `can_handle(command)` | method | Returns `True` if this processor should handle the given command string. |
| `process(command, output)` | method | Takes the command and its raw output, returns a compressed version. |

### Priority conventions

| Range | Category | Examples |
|-------|----------|---------|
| 10-19 | High priority overrides | PackageListProcessor (15) — must run before BuildOutputProcessor |
| 20-29 | Core processors | git (20), test (21), build (25), lint (27) |
| 30-49 | Specialized tools | network (30), docker (31), kubectl (32), terraform (33), env (34), search (35), system_info (36) |
| 50-69 | Content-based | file_listing (50), file_content (51) |
| 999 | Generic fallback | GenericProcessor — always last, do not use this value |

When choosing a priority:
- Pick a value in the appropriate range for your processor category.
- If your processor must run **before** another (e.g., to avoid misrouting), use a lower number.
- Leave gaps between values to allow future insertions without renumbering.

### hook_patterns

These are regex patterns that the pre-tool hook uses to decide whether to
intercept a command for compression. They should match the **start** of
commands your processor handles.

- Use `^` anchors so patterns match the beginning of the command.
- Patterns are compiled with `re.compile()` and matched with `re.search()`.
- GenericProcessor should have `hook_patterns = []` (it's a fallback).

### How auto-discovery works

1. `processors/__init__.py` scans all `.py` files in the `processors/` directory.
2. It imports each module and finds all non-abstract `Processor` subclasses.
3. Instances are sorted by `priority` (ascending).
4. `discover_processors()` returns the sorted list (used by `engine.py`).
5. `collect_hook_patterns()` collects all `hook_patterns` (used by `hook_pretool.py`).

---

## Adding tests

Tests for processors live in `tests/test_processors.py`. Each
processor has its own test class. Add a new class following this pattern:

```python
class TestMyToolProcessor:

    def setup_method(self):
        self.p = MyToolProcessor()

    def test_can_handle(self):
        # Commands your processor should match
        assert self.p.can_handle("mytool subcommand1")
        assert self.p.can_handle("mytool subcommand2 --flag")
        # Commands it should NOT match
        assert not self.p.can_handle("othertool run")
        assert not self.p.can_handle("ls -la")

    def test_empty_output(self):
        result = self.p.process("mytool subcommand1", "")
        assert result == ""

    def test_short_output_unchanged(self):
        output = "one line of output"
        result = self.p.process("mytool subcommand1", output)
        assert result == output

    def test_compression_logic(self):
        # Build a realistic output that should be compressed
        lines = [f"processing item {i}" for i in range(100)]
        lines.append("Done: 100 items processed")
        output = "\n".join(lines)

        result = self.p.process("mytool subcommand1", output)
        assert len(result) < len(output)
        # Verify important information is preserved
        assert "100 items processed" in result
```

Don't forget to add the import at the top of `test_processors.py`:

```python
from src.processors.my_tool import MyToolProcessor
```

You should also add an **integration test** in `test_engine.py` to verify
your processor is picked up by the engine:

```python
def test_mytool_output_compressed(self):
    output = "\n".join(f"item {i}" for i in range(100))
    compressed, processor, was_compressed = self.engine.compress(
        "mytool subcommand1", output
    )
    assert was_compressed
    assert processor == "my_tool"
```

And a **hook test** in `test_hooks.py` to verify the hook intercepts your
commands:

```python
def test_mytool_commands_compressible(self):
    assert is_compressible("mytool subcommand1")
    assert is_compressible("mytool subcommand2 --verbose")
```

### What to test

| Category | What to check |
|----------|---------------|
| `can_handle` | Positive matches, negative matches, edge cases |
| Empty/short output | Returns input unchanged |
| Compression | Output is shorter, key information is preserved |
| Error preservation | Error messages, stack traces, failure details are never dropped |
| Edge cases | Unicode, very long lines, unusual formatting |

### Running tests

```bash
python3 -m pytest tests/ -v
```

All existing tests must continue to pass after adding a new processor.
