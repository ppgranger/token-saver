# Syslog Processor

**File:** `src/processors/syslog.py` | **Priority:** 42 | **Name:** `syslog`

Handles system log output from `journalctl` and `dmesg`.

## Supported Commands

| Command | Strategy |
|---|---|
| `journalctl` | Head/tail compression with error extraction |
| `dmesg` | Same strategy |

## Compression Strategy

Uses the shared `compress_log_lines()` utility:

- **Head:** First 10 lines preserved (boot/startup messages)
- **Tail:** Last 20 lines preserved (most recent entries)
- **Errors:** Lines matching error/exception/fatal/panic/traceback patterns are preserved with 2 lines of context
- **Error cap:** Maximum 50 error-related lines to prevent explosion on noisy logs
- **Threshold:** Output with 30 or fewer lines passes through unchanged

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `file_log_context_lines` | 2 | Context lines around errors in log output |
