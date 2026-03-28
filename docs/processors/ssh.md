# SSH Processor

**File:** `src/processors/ssh.py` | **Priority:** 43 | **Name:** `ssh`

Handles non-interactive SSH and SCP command output.

## Supported Commands

- `ssh host 'command'` or `ssh host "command"` (non-interactive SSH with quoted remote command)
- `ssh -o Option=value host 'command'` (with SSH options)
- `scp` (all forms — always non-interactive)

## Not Supported

- `ssh host` (interactive SSH — no remote command) remains excluded from compression

## Strategy

| Command | Strategy |
|---|---|
| **SSH remote** | Apply log-style compression: keep first 10 + last 20 lines, preserve error lines with context in the middle section |
| **SCP** | Collapse progress bar lines (containing `%` and transfer rates) to final status per file. Keep error lines (permission denied, connection refused, etc.) |

## How It Works

The SSH/SCP exclusion in `hook_pretool.py` was narrowed from a blanket `ssh|scp` exclusion to only exclude interactive SSH (no quoted command). This allows:
- `ssh host 'ls -la'` — compressed (non-interactive)
- `scp file host:/path` — compressed (always non-interactive)
- `ssh host` — still excluded (interactive)
