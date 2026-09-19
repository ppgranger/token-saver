# Repository automation

- Enforce the root Google Python style policy through Ruff and the vendored
  `.pylintrc`. Keep Ruff 0.15.15 and Pylint 4.0.5 aligned with the development
  dependencies and contributor commands; retain the configuration's upstream
  license. Ruff owns quote normalization, while Pylint owns its other checks.
- Preserve the CI matrix: multiple supported Python versions on Linux plus
  macOS/Windows coverage for installation and shell differences.
- Keep lint, formatting, type checking, version consistency, tests, and the
  explicit-encoding check as independent enforceable checks. Do not mask
  failures with `continue-on-error`, broad ignores, or reduced assertions.
- Use minimal workflow permissions and retain concurrency cancellation for
  superseded pull-request runs. Fork pull requests must not gain write access
  or execute untrusted code with secrets through a changed event/checkout path.
- Pin tools consistently with the project's local workflow; update tooling
  deliberately and verify the resulting checks before changing versions.
- Do not add publishing or deployment steps as a side effect of test changes.
  Issue/PR templates should ask for reproducible inputs with secrets removed.
