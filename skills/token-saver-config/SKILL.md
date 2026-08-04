---
name: token-saver-config
description: "Configure and diagnose token-saver compression settings. Use when the user asks about adjusting compression levels, checking processor status, debugging hook issues, or reviewing savings statistics."
---

# Token-Saver Configuration & Diagnostics

## Check Status
Run `token-saver stats` to see lifetime and per-command compression statistics. Add `--json` for machine-readable output.

## Check Why a Specific Command Was (or Wasn't) Compressed
There is no `token-saver config` subcommand — use `explain` and `benchmark` instead:

```bash
token-saver explain "git status"          # routing decision: compressible? which processor? why excluded?
token-saver benchmark "npm install" --dry-run   # measure compression without replacing real output
```

## Configuration
Settings are read in this order (later wins): built-in defaults → `~/.token-saver/config.json` → a project-level `.token-saver.json` found by walking up from cwd → `TOKEN_SAVER_*` environment variables. There is no CLI subcommand to write these files — edit `~/.token-saver/config.json` directly, or set an environment variable.

The most commonly adjusted settings and their actual defaults:
- `enabled` (bool, default `true`): master on/off switch.
- `min_input_length` (int, default `1`): minimum output length in characters before compression is attempted.
- `min_compression_ratio` (float, default `0.0`): a compression result below this fraction is discarded and the original output is returned instead.
- `wrap_timeout` (int, default `300`): max seconds a wrapped command may run before being killed.
- `chars_per_token` (int, default `4`): used only to estimate token counts for display (stats, benchmark) — not part of compression itself.
- `disabled_processors` (list, default `[]`): processor names (e.g. `"docker"`, `"kubectl"`) to turn off entirely.
- `max_output_bytes` (int, default `10_000_000`): hard cap on output length before compression even runs.

Example `~/.token-saver/config.json`:
```json
{
  "min_compression_ratio": 0.1,
  "disabled_processors": ["docker"]
}
```

Equivalent environment variables: `TOKEN_SAVER_MIN_COMPRESSION_RATIO=0.1`, `TOKEN_SAVER_DISABLED_PROCESSORS=docker`.

**Security note:** `user_processors_dir`, `disabled_processors`, and `redaction_allowlist` can only be set via the global `~/.token-saver/config.json` or an environment variable — never via a project-level `.token-saver.json` (that file is auto-discovered from any directory you `cd` into, so it is not trusted with these).

See `src/config.py`'s `_DEFAULTS` dict for the full, authoritative list of settings — this file lists only the ones users actually tune.

## Debug Mode
Set `TOKEN_SAVER_DEBUG=true` to enable debug logging to `~/.token-saver/hook.log` (or `%APPDATA%\token-saver\hook.log` on Windows).

## Supported Processors
36 specialized processors, auto-discovered from `src/processors/`: git, gh (GitHub CLI), docker, kubectl, helm, terraform, pulumi, cdktf, ansible, nix, mise, npm/pip/cargo/go/maven/gradle/bun, package listing, python install, test runners (pytest, jest, go test, cargo test, …), lint output (eslint, ruff, pylint, clippy, …), build output, cloud CLIs (aws, gcloud, az), database queries, file listings, file content, environment/system info, network tools (curl, wget), search (grep, find, ripgrep), structured logs, syslog, ssh, jq/yq, act, just — plus a generic fallback for everything else.

## Troubleshooting
If compression isn't working:
1. Check that `python3` (3.10+) is available in your PATH.
2. Run `token-saver explain "<the command>"` to see the routing decision and why it was or wasn't wrapped.
3. Set `TOKEN_SAVER_DEBUG=true`, trigger a compressible command, then check `~/.token-saver/hook.log` for errors.
4. Verify the hook itself responds correctly:
   ```bash
   echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hook_pretool.py"
   ```
   A working hook prints a JSON object with `hookSpecificOutput.updatedInput.command` rewritten to invoke `wrap.py`.
