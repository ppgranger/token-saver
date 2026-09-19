# Working on Token-Saver

Token-Saver is a Python 3.10+ CLI-output compressor, with Claude Code and
Antigravity adapters and a Jekyll documentation site. Compression runs locally
and deterministically, without an LLM or network call in the compression path.

## Read the relevant instructions

This file applies to the repository. A nested `AGENTS.md` adds guidance for its
directory; read it before editing there. `CLAUDE.md` describes plugin behavior
and shell exclusions. Keep those guarantees consistent with code and tests.

## Python style

Use the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
as the review standard; `CONTRIBUTING.md` documents project tooling and exceptions.

- Format Python to 80 columns. Preserve literal fixture data when wrapping would
  change its meaning; justify any narrow exception rather than disabling a rule.
- Import modules by absolute package names and qualify their members. Typing
  symbols from `typing`, `typing_extensions`, and `collections.abc` are exempt.
- Write meaningful Google-style docstrings for public interfaces and nontrivial
  behavior. Describe relevant `Args`, `Returns`/`Yields`, `Raises`, and public
  `Attributes`; do not mechanically restate signatures or test names.
- Keep comprehensions simple: one `for` clause and at most one filter. Use loops
  for nested traversal and preserve processing order.
- Catch specific exceptions. A broad catch requires an explicit isolation
  boundary or re-raise; record suppressed failures without commands, captured
  output, secrets, exception text, or traceback locals.
- Include the repository's Apache 2.0 header in Python files. Preserve
  third-party copyright and license notices, including `.pylintrc`.
  Explain unavoidable local suppressions beside the relevant code.

## Design and compatibility

- Keep parsing/compression, orchestration, persistence, CLI presentation, and
  platform integration separate. Prefer small interfaces and injected
  dependencies where a real boundary exists; avoid abstract wrappers that add
  no behavior or independent test seam.
- Extend the processor contract for a new command family instead of adding
  command-specific branches to the engine or platform hooks.
- Preserve public CLI behavior, processor extension points, return shapes, and
  installed-tree imports during refactors. New `src` subpackages need explicit
  packaging and installer coverage; current copying discovers top-level source
  modules and processor modules.
- Preserve failure details and secret redaction ahead of compression ratios.
  A redacted result must never be replaced by its unredacted input merely
  because a size threshold was not met.
- Follow the existing Python 3.10 syntax and standard-library runtime approach.
  Use explicit UTF-8 for text files and text subprocess output.

## Validation

Run targeted tests while iterating. Before finishing changes to runtime code,
run the applicable repository checks (the CI workflow is authoritative):

```sh
python3 -m pytest tests/ -q
ruff check . bin/token-saver
ruff format --check . bin/token-saver
python3 scripts/check_python_style.py
pylint --rcfile=.pylintrc src scripts installers antigravity/hook_aftertool.py \
  install.py examples/demo.py examples/custom_processor/ansible_output.py \
  bin/token-saver
mypy src/ scripts/ --ignore-missing-imports
python3 scripts/check_versions.py
```

Use Ruff 0.15.15 and Pylint 4.0.5, matching `pyproject.toml` and the CI workflow.
The vendored Google Pylint configuration and Ruff serve complementary checks;
Ruff owns quote normalization. For text I/O changes, also run the encoding check:

```sh
PYTHONWARNDEFAULTENCODING=1 python3 -W error::EncodingWarning -m pytest tests/ -q
```

Use temporary homes/data directories for installer, tracker, and config tests.
Do not run installation, update, or uninstall commands against the developer's
real profile just to validate a change. A normal `benchmark` and the wrapper's
`--dry-run` execute their supplied command; use harmless fixture commands.
CLI `benchmark --dry-run` only inspects routing, and `benchmark --stdin` uses
already captured output without executing the command.

## Keep public facts in sync

- Configuration defaults: `src/config.py` and the README's **Complete Parameter
  List**; `tests/test_readme_config_sync.py` enforces both values and trust notes.
- Processor additions/removals: discovery is automatic, but update public
  counts, documentation, failure fixtures, and relevant benchmark scenarios.
  Run `tests/test_processor_count_consistency.py` and
  `tests/test_pattern_consistency.py`.
- Releases: `src/__init__.py` is the version source. Synchronize both Claude
  manifests, the Antigravity manifest, the benchmark version header, and a
  matching changelog entry; `scripts/check_versions.py` checks this. A routine
  refactor does not require inventing a release or bumping the version.
- Document measured savings as estimates with a reproducible scenario; do not
  turn selective compression or tested preservation into universal guarantees.
