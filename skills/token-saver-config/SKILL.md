---
name: token-saver-config
description: "Configure and diagnose token-saver compression settings. Use when the user asks about adjusting compression levels, checking processor status, debugging hook issues, or reviewing savings statistics."
---

# Token-Saver Configuration & Diagnostics

## Check Status
Run `token-saver stats` to see compression statistics for the current and all sessions.

## Configuration
Token-saver config is stored in `~/.token-saver/config.json`. Available settings:
- `min_lines`: minimum output lines to trigger compression (default: 5)
- `min_chars`: minimum output chars to trigger compression (default: 200)
- `chars_per_token`: ratio for token estimation (default: 3.5)
- `wrap_timeout`: max seconds for command execution (default: 30)

To modify: `token-saver config set min_lines 10`

## Debug Mode
Set `TOKEN_SAVER_DEBUG=true` environment variable to enable debug logging to `~/.token-saver/hook.log`.

## Supported Processors
Token-saver includes processors for: git, gh (GitHub CLI), docker, kubectl, terraform, npm/pip/cargo, test runners (pytest, jest, go test), linters (eslint, ruff, pylint), build tools, cloud CLIs (aws, gcloud, az), database queries, file listings, file content, environment/system info, network tools (curl, wget), and search (grep, find, ripgrep).

## Troubleshooting
If compression isn't working:
1. Check that `python3` is available in your PATH
2. Run `TOKEN_SAVER_DEBUG=true` then trigger a compressible command
3. Check `~/.token-saver/hook.log` for errors
4. Verify with: `echo "test" | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hook_pretool.py"`
