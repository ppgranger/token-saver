# Token-Saver Plugin

Token-saver automatically compresses verbose CLI output to save tokens.

## How it works
- A PreToolUse hook intercepts Bash commands matching known patterns (git, docker, npm, terraform, kubectl, etc.)
- The command output is piped through specialized compression processors
- Compressed output is returned to Claude, saving tokens while preserving critical information

## Important rules
- Never wrap `token-saver` CLI commands themselves (avoid infinite loops)
- Never wrap interactive commands (vim, nano, ssh, etc.)
- Never wrap commands with redirections (>) or complex pipes
- Never wrap sudo commands
- Debug mode: set TOKEN_SAVER_DEBUG=true environment variable
