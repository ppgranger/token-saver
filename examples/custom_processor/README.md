# Writing Custom Processors

Token-Saver supports user-defined processors loaded from `~/.token-saver/processors/`.

## Quick Start

1. Create a Python file with a class that inherits from `src.processors.base.Processor`
2. Implement `can_handle()`, `process()`, `name`, and set `priority`
3. Copy the file to `~/.token-saver/processors/`

```bash
# Install the example ansible processor
cp examples/custom_processor/ansible_output.py ~/.token-saver/processors/
```

## Processor Interface

Every processor must implement:

- **`priority`** (class attribute, `int`): Determines evaluation order. Lower = checked first. See priority conventions below.
- **`hook_patterns`** (class attribute, `list[str]`): Regex patterns for commands this processor handles. Used by the hook system.
- **`can_handle(command: str) -> bool`**: Return `True` if this processor should handle the given command.
- **`process(command: str, output: str) -> str`**: Compress the output. Return the compressed version.
- **`name`** (property, `str`): A short name for tracking/stats.

## Priority Conventions

| Range  | Usage |
|--------|-------|
| 10-19  | High priority overrides |
| 20-29  | Core processors (git, test, build, lint) |
| 30-49  | Specialized (network, docker, kubectl, terraform) |
| 50-69  | Content-based (file listing, file content) |
| 999    | Generic fallback (reserved, do not use) |

User processors can use any priority. To override a built-in processor, use a lower priority value than the one you want to replace.

## Example

See `ansible_output.py` in this directory for a complete example.

## Custom Directory

By default, user processors are loaded from `~/.token-saver/processors/`. To change this, set `user_processors_dir` in your config:

```json
{
  "user_processors_dir": "/path/to/my/processors"
}
```

## Safety

- A broken user processor (syntax error, missing class, runtime error) is skipped with a warning — it never crashes the engine.
- Enable `TOKEN_SAVER_DEBUG=true` to see skip messages in stderr.
