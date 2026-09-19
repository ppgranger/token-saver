# Shipped assistant skills

- Python snippets follow the root Google Python style policy: 80 columns,
  absolute module imports, and useful contract documentation. Contributor
  guidance must name the actual pinned Ruff/Pylint checks rather than claiming
  that passing a formatter establishes complete guide compliance.
- Skills describe the installed CLI and configuration that actually exist.
  Verify commands against `src/cli.py` and defaults against `src/config.py`;
  do not invent a configuration command or an unsupported flag.
- Keep precedence and the project-configuration restrictions explicit. Never
  recommend enabling arbitrary processor loading or weakening redaction from
  a repository-controlled project configuration.
- Diagnostics must distinguish routing inspection (`benchmark --dry-run`),
  captured-output compression (`benchmark --stdin`), and normal benchmark
  execution. The wrapper's separate `--dry-run` option does execute its command;
  do not conflate the two dry-run modes or use destructive examples.
- Keep supported-processor counts and capabilities synchronized with discovery.
  Run `tests/test_processor_count_consistency.py` after changing those claims.
- Preserve `SKILL.md` front matter and deployed paths used by installers.
  Troubleshooting examples should keep hook stdout valid JSON and direct debug
  information to its configured logging destination.
