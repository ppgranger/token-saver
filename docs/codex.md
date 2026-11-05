---
title: Codex setup
description: Use Token-Saver from Codex with an explicit shell wrapper and project instructions, preserving command exit status without installing Claude hooks.
permalink: /codex/
nav_order: 9
---

# Use Token-Saver with Codex

Codex can invoke Token-Saver's existing shell wrapper explicitly. This is an
opt-in workflow for ordinary compression; Token-Saver does not ship a Codex
hook or an `install.py --target codex` adapter. Commands that Codex runs without
the wrapper remain unchanged. Experimental Delta integration remains limited
to Claude Code.

## Prepare a local checkout

Use Python 3.10 or later in the environment where Codex executes commands.
Clone Token-Saver into a stable directory accessible to that environment:

```bash
git clone https://github.com/ppgranger/token-saver.git
python3 token-saver/bin/token-saver version
```

No Claude Code installation, marketplace setup, or Python dependencies are
needed for this workflow. In a remote environment, provision the checkout and
Python there as well; a path on your laptop is not automatically available.

From the project you are working on, replace the example path below with the
absolute path to the checkout. Use an absolute Python executable path too if
`python3` does not select a supported interpreter:

```bash
python3 /absolute/path/token-saver/scripts/wrap.py 'git status'
python3 /absolute/path/token-saver/scripts/wrap.py 'python3 -m pytest -q'
```

Keep the original command inside one quoted argument. The wrapper runs it once
in the current working directory, compresses captured output, and returns the
command's exit status. It buffers output, so use it for bounded, noninteractive
commands. A timeout returns partial output and status `124`; `wrap_timeout`
controls that limit. Ordinary savings statistics use the current user's
Token-Saver data directory. This shared wrapper records its platform as
`claude_code`, so those statistics do not distinguish Codex runs.

## Add project instructions

Codex reads project `AGENTS.md` instructions. Append a small section to your
existing file, replacing the path and interpreter to match your environment:

```markdown
## Token-Saver output compression

For verbose, noninteractive test, lint, build, and git inspection commands,
invoke this wrapper from the project's working directory:
python3 /absolute/path/token-saver/scripts/wrap.py '<original command>'

Keep the original command as one shell-quoted argument. Preserve its exit
status and do not rerun a failing command just to obtain uncompressed output.
Use ordinary tools for exact source reads and edits, interactive commands,
sudo, redirections, and complex shell pipelines. Do not wrap token-saver
itself or a command already using wrap.py. Normal sandbox and approval rules
still apply to the original command.
```

Start a new Codex session after changing project instructions and ask it to
run a suitable command through the wrapper. These instructions guide the
agent; they do not intercept every shell call. See the official
[AGENTS.md documentation](https://developers.openai.com/codex/guides/agents-md)
for instruction discovery and precedence.

## Verify the workflow

Inspect eligibility without executing the supplied command:

```bash
python3 /absolute/path/token-saver/bin/token-saver explain 'git status'
python3 /absolute/path/token-saver/bin/token-saver benchmark 'git status' --dry-run
```

Then try a harmless success and failure in a POSIX shell:

```bash
python3 /absolute/path/token-saver/scripts/wrap.py 'printf "hello\n"'
python3 /absolute/path/token-saver/scripts/wrap.py 'sh -c "echo ERROR: demo >&2; exit 7"'
printf 'Exit status: %s\n' "$?"
```

The first command prints `hello`; the second retains `ERROR: demo` and reports
exit status `7`. On POSIX systems the wrapper runs commands through `/bin/sh`,
so avoid Bash-only syntax unless the command explicitly invokes Bash. On
Windows it uses Git Bash when available. WSL provides a POSIX environment;
use checkout and interpreter paths belonging to that environment.

The wrapper's own `--dry-run` **executes** the command and returns raw output.
It is different from the CLI's `benchmark --dry-run` above. For already
captured logs, use [offline compression and quality gates](quality-gates.md)
to avoid executing the command again. Compression may omit detail; read exact
source directly and validate required diagnostics for your workflow.

To stop using this integration, remove the instruction section and invoke
commands normally. The checkout can stay available for occasional explicit
use.
