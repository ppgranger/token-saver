# Contributing to Token-Saver

## How to contribute

This project uses a **fork-based workflow**. Direct pushes to `main` are not
allowed — all changes go through pull requests reviewed by maintainers.

### 1. Fork and clone

```bash
# Fork the repo on GitHub (click the "Fork" button), then:
git clone https://github.com/<your-username>/token-saver.git
cd token-saver
python3 -m pip install -e ".[dev]"
```

### 2. Create a branch

```bash
git checkout -b my-feature
```

### 3. Make your changes

Edit the code, add tests, and make sure everything passes locally:

```bash
# Style and types
ruff check . bin/token-saver
ruff format --check . bin/token-saver
python3 scripts/check_python_style.py
pylint --rcfile=.pylintrc src scripts installers antigravity/hook_aftertool.py \
  install.py examples/demo.py examples/custom_processor/ansible_output.py \
  bin/token-saver
mypy src/ scripts/ --ignore-missing-imports

# Tests and release consistency
python3 -m pytest tests/ -q
python3 scripts/check_versions.py
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
- CI runs **Ruff**, **Pylint**, **mypy**, version and documentation checks, and
  **pytest**. The test matrix covers Python 3.10–3.13 on Linux and Python 3.12
  on macOS and Windows; `.github/workflows/ci.yml` is authoritative.
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

Python changes are reviewed against the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
Read the root `AGENTS.md` and any instructions in the directory you change.
The project supports Python 3.10+ and keeps runtime dependencies in the standard
library.

Use **Ruff 0.15.15** and **Pylint 4.0.5**, installed by the development extra.
Ruff formatting, import ordering, and Google docstring checks are configured in
`pyproject.toml`. `.pylintrc` vendors Google's official configuration with its
copyright and Apache 2.0 notice intact. Its project adjustments are:

- `jobs=1` keeps local and CI checks predictable across hosts.
- Pylint's `inconsistent-quotes` check is disabled because Ruff normalizes
  quoting and permits alternate quotes where they avoid unnecessary escapes.

`scripts/check_python_style.py` supplements these tools with syntax-tree checks
for absolute module imports and simple comprehensions. It checks runtime code,
scripts, installers, examples, tests, and the CLI launcher without importing any
checked code. Module resolution examines project and interpreter library paths;
dynamic re-exports are outside its static checks.

Keep Python code to 80 columns. Use absolute module imports and qualify members,
for example `from src.processors import base` and `base.Processor`. Imports used
for typing from `typing`, `typing_extensions`, and `collections.abc` retain the
guide's exemption. Keep comprehensions to one `for` clause and at most one
filter; use explicit loops for nested traversal.

Public interfaces need useful contracts, including relevant `Args`, `Returns`
or `Yields`, `Raises`, and public `Attributes`. Explain side effects, units,
failure behavior, and preservation limits where they matter. Do not add empty
sections or repeat information that a short, clear signature already conveys.

Catch specific failures unless the code re-raises or protects an explicit
isolation boundary. When suppressing a failure at such a boundary, record a
content-free diagnostic. Never log command strings, captured output, secrets,
exception text, or traceback locals. Preserve earlier redactions on recovery.

Keep exceptions narrow and explain them beside the affected code. Exact integer
validation, for example, can reject booleans and numeric subclasses deliberately.
Tests retain missing-docstring exemptions for readable pytest cases and fixtures;
explanatory test documentation remains useful for non-obvious scenarios. Raw
fixture lines may need a justified line-length exception to preserve their
meaning. Include the repository's Apache 2.0 header in new Python files; keep
existing copyright and license notices when editing or copying licensed files.

```bash
# Check for lint issues
ruff check . bin/token-saver

# Auto-fix safe issues
ruff check --fix .

# Check formatting
ruff format --check . bin/token-saver

# Auto-format
ruff format .

# Run the vendored Google Pylint rules over executable project code
pylint --rcfile=.pylintrc src scripts installers antigravity/hook_aftertool.py \
  install.py examples/demo.py examples/custom_processor/ansible_output.py \
  bin/token-saver

# Check imports and comprehension structure without loading project modules
python3 scripts/check_python_style.py
```

Run all validation commands from step 3 before proposing a runtime change.
For text I/O changes, also check that tests do not depend on the locale encoding:

```bash
PYTHONWARNDEFAULTENCODING=1 python3 -W error::EncodingWarning -m pytest tests/ -q
```

Automated checks cover enforceable rules; reviewers still assess clarity,
documentation quality, interface design, and the justification for exceptions.
Passing the tools is not a claim that every recommendation can be certified
automatically. Use temporary homes and data directories for installer, tracker,
and configuration tests, never the developer's real profile.

---

## Architecture changes

Follow the [architecture contracts](docs/architecture.md) when extending the
runtime. Keep command-family parsing in processors, eligibility in
`src/command_policy.py`, shell execution in adapters, optional writes in
`src/telemetry.py`, storage in its concrete stores, and presentation in CLI or
pure formatting functions. Comparison rules belong in `src/diagnostics.py` and
must be shared by display and detail-preservation decisions.

Prefer explicit dependencies at a real replacement or resource boundary.
Preserve historical APIs with small compatibility facades when moving code.
Keep imports free of filesystem/database initialization. Exercise meaningful
failure paths and prove installed-tree imports when adding a runtime module.
Do not add an abstract interface simply to forward a function call; the existing
small contracts cover processor discovery, compression, policy, and recording.

## Adding a new processor

Create a processor module in `src/processors/` and it will be automatically
discovered. Registration needs no central edit; tests, documentation, failure
fixtures, and published processor counts still need to reflect the addition.

### Quick start

1. Create `src/processors/my_tool.py`
2. Add routing, preservation, hook, and engine tests plus a failure fixture.
3. Update the relevant documentation and processor counts.
4. Run the root validation commands and the processor consistency tests.

See `src/processors/AGENTS.md` for the processor-specific checks.

### Processor template

```python
"""MyTool output processor: describe what it handles."""

import re

from src.processors import base


class MyToolProcessor(base.Processor):
    """Handle MyTool subcommands while preserving unrecognized output.

    Attributes:
        priority: Routing priority relative to other processors.
        hook_patterns: Anchored patterns that select this command family.
    """

    priority = 40  # See priority conventions below.
    hook_patterns = [
        r"^mytool\s+(subcommand1|subcommand2)\b",
    ]

    @property
    def name(self) -> str:
        """Return the stable processor identifier."""
        return "my_tool"

    def can_handle(self, command: str) -> bool:
        """Return whether the command names a supported MyTool subcommand."""
        return bool(
            re.search(r"\bmytool\s+(subcommand1|subcommand2)\b", command)
        )

    def process(self, command: str, output: str) -> str:
        """Transform supported output while retaining unknown shapes.

        Args:
            command: Command label; this method never executes it.
            output: Captured output to inspect.

        Returns:
            The input unchanged until command-specific compression is added.
        """
        del command  # Unused by this starting template.
        if not output or not output.strip():
            return output
        # Add and test command-specific compression here.
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
from src.processors import my_tool


class TestMyToolProcessor:

    def setup_method(self):
        self.p = my_tool.MyToolProcessor()

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

Keep the module import at the top of `test_processors.py`. The compression test
is a behavior to implement; it will fail against the unchanged starting template.

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
from scripts import hook_pretool


def test_mytool_commands_compressible(self):
    assert hook_pretool.is_compressible("mytool subcommand1")
    assert hook_pretool.is_compressible("mytool subcommand2 --verbose")
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

## Releasing

`src/__init__.py` holds `__version__` and is the single source of truth — the
installer stamps the manifests from it. But the copies committed in the repo are
what users resolve against, and Claude Code keys its update cache on
`.claude-plugin/plugin.json`: **a release that forgets to bump that file reaches
nobody**, and `/plugin update` reports "already on the latest version".

So a release commit touches all five:

| File | Where |
|------|-------|
| `src/__init__.py` | `__version__` |
| `.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` | `plugins[0].version` |
| `antigravity/antigravity-plugin.json` | `version` |
| `docs/benchmarks.md` | `Version: **X.Y.Z**` header line |

Plus a new `## [X.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md`.

Verify before pushing — CI runs the same check and fails the PR otherwise:

```bash
python3 scripts/check_versions.py
```

Version numbers follow [semver](https://semver.org): MAJOR for breaking changes,
MINOR for new features, PATCH for bug fixes. Tag the merge commit `vX.Y.Z`.
