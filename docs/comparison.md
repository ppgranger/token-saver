# How Token-Saver Compares

Token-Saver focuses specifically on **command output compression** — it doesn't cache, delegate, or summarize via LLM. The tools below solve adjacent but different problems, and in many cases can be used alongside Token-Saver.

## Comparison Table

| Feature | Token-Saver | cc_token_saver_mcp | token-optimizer-mcp | Claude Context Mode |
|---------|------------|-------------------|--------------------|--------------------|
| **Approach** | Deterministic compression per command type | Delegates simple tasks to local LLM | Caching + compression via MCP | Sandboxed execution + FTS5 indexing |
| **Requires LLM calls** | No | Yes (local LLM) | Yes | No |
| **Added latency** | ~0ms (regex/parsing only) | Variable (LLM inference) | Variable | ~0ms for sandbox, variable for indexing |
| **Platform support** | Claude Code, Antigravity CLI | Claude Code only | Claude Code only | Claude Code only |
| **Compression method** | 36 specialized processors (git, pytest, cargo, go, terraform, pulumi, docker, k8s...) | Task delegation (not output compression) | Response caching | Output sandboxing + summarization |
| **Preserves all errors/traces** | Yes (precision-tested) | N/A | Depends on cache hit | Depends on summary |
| **Works offline** | Yes | Needs local LLM running | No | Yes |
| **Install complexity** | `python3 install.py` | MCP server config | MCP server config | MCP skill install |

## Key Differences

### Token-Saver

Token-Saver intercepts command output and applies **deterministic, per-command compression** using 36 specialized processors. It understands the structure of `git diff`, `pytest`, `terraform plan`, and other common CLI outputs, and removes only noise (progress bars, passing tests, installation logs) while preserving all actionable information (errors, diffs, warnings).

- Zero latency overhead (regex and string parsing only)
- Fully deterministic — same input always produces same output
- Works offline, no external dependencies
- 853 tests including precision tests that verify critical data survives compression
- Supports both Claude Code and Antigravity CLI

### cc_token_saver_mcp

An MCP server that intercepts tool calls and delegates simple tasks (like reading files or listing directories) to a local LLM instead of Claude. This reduces token usage by avoiding Claude entirely for trivial operations. It's a different strategy — **task delegation** rather than output compression. Can be used alongside Token-Saver.

### token-optimizer-mcp

An MCP-based tool that caches and compresses responses. Useful for repetitive queries where the same command is run multiple times. Complements Token-Saver's single-pass compression with cross-invocation caching.

### Claude Context Mode

A skill for Claude Code that runs commands in a sandboxed environment and indexes outputs for later retrieval via FTS5. Useful for managing very large codebases where full context doesn't fit. Solves a different problem — **context management** rather than output compression.

## Can I Use Them Together?

Yes. Token-Saver operates at the output level (compressing what the model sees), while the other tools operate at the task level (delegating), caching level (avoiding re-computation), or context level (indexing). They are complementary, not competing.
