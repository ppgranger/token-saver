# Generic Processor (Fallback)

**File:** `src/processors/generic.py` | **Priority:** 999 | **Name:** `generic`

Universal fallback processor. Applies to any command not recognized by specialized processors, and also serves as a second-pass cleaner after specialized processors.

## Strategy

Applied in order:

1. **ANSI code stripping** -- colors, formatting, OSC sequences
2. **Progress bar stripping** -- lines that are mostly bar characters (`━`, `█`, `▓`, `░`, `#`, `=`, `>`, `-`, etc.). Must be > 50% bar characters
3. **Blank line collapse** -- consecutive blank lines merged into one
4. **Identical line collapse** -- consecutive identical lines: `line (x47)`
5. **Similar line collapse** -- consecutive lines differing only in numbers/percentages: keeps first + last + count. Only applies to "numeric-heavy" lines (> 25% digits, or containing percentages/transfer rates/ETA patterns). Targets curl/wget progress while preserving meaningful data
6. **Middle truncation** -- if > 500 lines: keeps first 200 + last 100

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `generic_truncate_threshold` | 500 | Lines before middle truncation |
| `generic_keep_head` | 200 | Lines kept from start |
| `generic_keep_tail` | 100 | Lines kept from end |

## Clean Pass

The `clean()` method is called by the engine after every specialized processor. It applies only:
- ANSI code stripping
- Blank line collapse
- Trailing whitespace removal

This ensures no ANSI codes or excessive whitespace leak through even after specialized processing.

## Engine Fallback

When a specialized processor handles a command but doesn't achieve the minimum compression ratio (10%), the engine tries the generic processor as a fallback before returning uncompressed output. This catches cases where the specialized processor recognizes the command but the output doesn't match expected patterns.
