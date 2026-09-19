# Tests and fixtures

- Apply the root Google Python style policy to test code and module imports.
  Named pytest cases and fixtures retain the missing-docstring exemptions in
  `pyproject.toml`; add prose when it explains a non-obvious scenario. Keep raw
  captured fixtures intact and justify narrow line-length exceptions where
  splitting a line would change the tested data.
- Test externally visible behavior and meaningful boundary failures. For
  compression, assert which actionable lines survive as well as whether output
  gets shorter; a length assertion alone cannot detect lost errors.
- Use realistic success and failure output, Unicode, empty output, and relevant
  quoting/path variants. A known nonzero exit status must not yield a fabricated
  success result. Use inert synthetic secrets for redaction assertions.
- Isolate configuration caches, environment overrides, cwd, processor discovery,
  and SQLite paths. Use `tmp_path`/`monkeypatch`; keep installer subprocesses
  inside the sandbox profile built by `test_install_smoke.py`.
- Use fixed, harmless subprocess commands. Give subprocesses timeouts and an
  explicit UTF-8 encoding for text mode. Preserve cross-platform coverage rather
  than skipping a failing platform to hide a regression.
- Put new processor failure cases in `failure_fixtures.py`. The shared corpus
  drives precision and hook-pattern checks; a processor with no reachable
  failure fixture leaves a production path unverified.
- `compression_baselines.json` records real routing and compression behavior.
  Do not loosen tolerances, remove a scenario, or refresh the file merely to
  make a regression pass. A justified baseline update needs a measured reason
  and preservation checks; regeneration instructions are in
  `test_compression_ratchet.py`.
- Public-content consistency tests protect processor counts, configuration
  defaults, and committed versions. Fix the source/document mismatch rather
  than weakening the assertion.

Run a focused test module first, then the root validation commands for changes
that cross runtime boundaries. Test names and fixtures should explain the
regression independently of the implementation being refactored.
