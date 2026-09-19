# Installation boundaries

- Apply the root Google Python style policy and Pylint check. Keep absolute
  module imports working in installed trees, document destructive side effects
  and recoverable failures, and preserve copied license notices.
- Keep shared file copying, version reading, path selection, and migrations in
  `common.py`; platform modules should own only platform registration details.
- Every new runtime dependency must reach installed copies. Top-level `src/*.py`
  and processor modules are discovered automatically; new subpackages or adapter
  scripts require explicit installer/package changes and installed-tree tests.
- Preserve both copy and symlink modes. Never overwrite through a destination
  symlink, delete the source when source and destination resolve to the same
  file, or remove unrelated user settings/plugin entries.
- Use the canonical version from `src/__init__.py` when stamping manifests.
  Installation stamping does not replace committed release consistency checks.
- Preserve macOS/Linux/Windows paths and interpreter handling. Do not hardcode
  a POSIX home layout for Windows. Keep plugin cache/marketplace registration
  formats compatible with the adapter tests.
- Make repeated install/uninstall operations predictable. Scope cleanup to
  Token-Saver's owned paths and keys; handle broken symlinks and legacy installs
  without following them into unrelated files.
- Validate through `tests/test_installers.py` and
  `tests/test_install_smoke.py`, which use temporary profiles. The smoke test
  must import and use the installed copy from outside the repository so missing
  shipped modules cannot be masked by the development checkout.

Do not run manual installer/update/uninstall validation against the developer's
real home directory.
