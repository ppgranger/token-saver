---
name: stats
description: "Show token-saver compression statistics and savings"
---

Run the token-saver stats command to display savings:

```bash
token-saver stats
```

If the `token-saver` CLI is not in PATH, use the bundled wrapper script (not
`src/cli.py` directly — it imports via the `src` package and needs the repo
root on `sys.path`, which only `bin/token-saver` sets up):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/token-saver" stats
```

Present a summary of tokens saved in the current session and overall.
