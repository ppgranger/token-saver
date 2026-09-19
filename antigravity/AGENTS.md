# Antigravity adapter

- Apply the root Google Python style policy. Document host input/output
  contracts, use absolute module imports, and record suppressed adapter failures
  without host payloads, captured output, exception text, or secrets.
- This is a platform adapter: parse host input through `src.platforms`, use
  `src.core` for shared eligibility/compression/recording, and emit the host's
  existing response shape. Do not duplicate processors or shell safety policy.
- Keep stdout machine-readable JSON with no status banners. Invalid input,
  absent output, skipped commands, and unchanged results must pass through
  according to the existing hook protocol without blocking the host tool.
- Preserve the replacement-output semantics of `decision`/`reason`. Add tests
  for malformed/missing host fields and redaction before changing that contract.
- Hook paths use the installed extension root, not the checkout's current
  directory. New imported modules/scripts must be included in
  `installers/antigravity.py` and verified in installer smoke tests.
- Keep `antigravity-plugin.json` version synchronized through the root release
  check. Match hook declarations to actual entry points and keep timeouts finite.

Use the Antigravity cases in `tests/test_hooks.py` and the shared core/platform
tests, plus installation tests when manifests or shipped paths change.
