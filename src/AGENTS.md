# Runtime boundaries

- Apply the root Google Python style policy. Use absolute module imports and
  document public contracts, including output shape, redaction, and failure
  behavior. Runtime error isolation must record only content-free diagnostics.
- Keep processors focused on transforming command output. Keep subprocess
  execution and platform JSON in adapters, persistence in the tracker, and
  presentation in CLI/stats code. The engine coordinates these contracts.
- Preserve `CompressionEngine.compress()` and `core.compress()` compatibility
  when moving implementation details. Existing callers and user processors
  must continue to work without platform-specific dependencies.
- Treat unavailable diagnostics/persistence as best effort: they must not
  prevent the user's command output from being returned. Do not silently turn
  a failed command into a successful result.
- On a known nonzero exit status, only processors that opt into failure handling
  may use specialized compression. Keep the generic fallback and critical-line
  recovery behavior covered by precision tests.
- Run redaction before accepting any fallback path that could disclose the
  original text. Redaction must also survive processor chaining, size gates,
  and error recovery; recovered lines must not reintroduce secrets.
- Keep configuration precedence: defaults, global file, project file,
  environment. Project configuration must not control `user_processors_dir`,
  `disabled_processors`, or `redaction_allowlist`. Validate values at the
  configuration boundary and update the README when defaults change.
- Token counts derived from `chars_per_token` are estimates. Do not label them
  exact model usage or billing savings.
- Reuse `data_dir()` and platform helpers for paths. Preserve Linux, macOS, and
  Windows behavior; tests must not depend on the developer's actual config,
  processor directory, or savings database.

For orchestration changes, start with `tests/test_engine.py`,
`tests/test_core.py`, `tests/test_precision.py`, and
`tests/test_compression_ratchet.py`. Run CLI/config/tracker tests when those
boundaries change. Read `src/processors/AGENTS.md` before editing processors.
