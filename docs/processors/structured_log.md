# Structured Log Processor

**File:** `src/processors/structured_log.py` | **Priority:** 45 | **Name:** `structured_log`

Processor for JSON Lines log output from log tailing tools.

## Supported Commands

stern, kubetail.

## Strategy

| Content Type | Strategy |
|---|---|
| **JSON Lines (>50% valid JSON)** | Parse each JSON object. Group entries by log level (error/warn/info/debug/trace). Show count per level. Extract and display error messages (up to 10). Detect level from common keys: `level`, `severity`, `log_level`, `lvl` |
| **Non-JSON output** | Fall back to log compression (head/tail with error preservation) |

## Level Detection

Checks these JSON keys in order: `level`, `severity`, `log_level`, `loglevel`, `lvl`, `log.level`. Falls back to regex matching on message content for `ERROR`/`WARN` patterns.

## Message Extraction

Checks these JSON keys in order: `msg`, `message`, `text`, `log`, `body`. Truncates messages longer than 200 characters.

## Configuration

| Parameter | Default | Description |
|---|---|---|
| kubectl_keep_head | 5 | Lines to keep from start (non-JSON fallback) |
| kubectl_keep_tail | 10 | Lines to keep from end (non-JSON fallback) |

## Future Use

This processor can be activated via `chain_to` from other processors for outputs that contain embedded JSON Lines.
