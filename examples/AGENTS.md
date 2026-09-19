# Executable examples

- Examples teach the root Google Python style policy as well as the API. Import
  modules by absolute names, subclass `base.Processor`, keep code to 80 columns,
  and explain nontrivial contracts with Google-style docstrings. Validate Python
  examples with the root Ruff and Pylint commands.
- Keep examples small, runnable, and consistent with the public processor/CLI
  contracts. A custom processor needs the same anchored hook patterns, routing,
  priorities, failure preservation, and redaction behavior as built-ins.
- Use synthetic output and harmless commands; examples must not require a real
  cloud account, production database, API key, or installation into the reader's
  home just to demonstrate compression.
- Distinguish sample output from measured benchmark results. If a demo claims a
  percentage, generate it with the current engine and estimator.
- Explain user-processor code loading and the global/environment-only trust
  boundary for `user_processors_dir`. Do not suggest setting it in project
  `.token-saver.json`.
- When the processor contract changes, update the custom-processor example and
  verify it with the user-processor tests.
