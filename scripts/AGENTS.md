# Hooks, shell execution, and maintenance scripts

- Apply the root Google Python style policy to entry points and maintenance
  scripts. Use absolute module imports after any required path bootstrap;
  justify that import placement locally. Document exit statuses and execution
  side effects, and record broad isolation failures without command/output data.
- Keep hook stdout valid for the host protocol. Send diagnostics to stderr or
  configured logging; malformed input and unavailable optional components must
  fail open without preventing the host from running the original command.
- Never recursively wrap Token-Saver's CLI or wrapper. Preserve exclusions for
  sudo, interactive/streaming/background commands, redirection, unsafe shell
  constructs, and unsupported pipelines. Safe trailing pipes and command chains
  have explicit existing rules; do not broaden them with naive string splitting.
- Use shared quote-aware shell helpers. Keep `explain_decision()` consistent
  with the actual wrapping decision so diagnostics report production behavior.
- Preserve command execution exactly once, original exit status, cwd/environment
  behavior, quoting, and `&&` short-circuit semantics. Markers inserted into
  chained output must never leak. Validate rewritten shell syntax before use.
- Use the same POSIX shell for parsing and execution. On Windows honor the
  existing Git Bash selection; do not send Bash commands to `cmd.exe`.
- Keep timeout/signal cleanup and partial output behavior. Never retry a command
  just because compression or tracking failed: commands may have side effects.
- `wrap.py --dry-run` executes the command and reports what compression would
  change. CLI `benchmark --dry-run` only inspects routing; normal `benchmark`
  executes unless `--stdin` supplies captured output. Preserve and document
  this distinction, and test execution modes with harmless commands.
- Benchmark/demo scripts must use reproducible fixtures. Report estimated
  tokens consistently with the runtime estimator and preserve version checks.

For hook/wrapper changes run `tests/test_hooks.py`, `tests/test_shell_syntax.py`,
`tests/test_cli.py`, and the affected engine/core tests. For release maintenance
run `python3 scripts/check_versions.py`.
