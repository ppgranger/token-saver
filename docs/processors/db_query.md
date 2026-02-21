# Database Query Processor

**File:** `src/processors/db_query.py` | **Priority:** 38 | **Name:** `db_query`

Handles database query result output.

## Supported Commands

psql, mysql, sqlite3, mycli, pgcli, litecli.

## Strategy

| Format | Strategy |
|---|---|
| PostgreSQL table (`\|` separators, `(N rows)` footer) | Keeps header + first 11 and last 10 data rows. Preserves row count footer |
| MySQL table (`+---+` borders) | Keeps header + first 11 and last 10 data rows. Preserves row count footer |
| CSV/TSV output | Keeps header + first 10 and last 5 data rows. Shows column count |
| Generic tabular | Keeps first 15 and last 5 lines |

## What is preserved

- Table headers (column names)
- First and last data rows (for context)
- Row count footers (`(N rows)`, `N rows in set`)
- Error messages
- Query timing information

## What is removed

- Middle data rows when result set exceeds threshold
- Decorative separator lines within data

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `db_max_rows` | 20 | Maximum data rows shown before truncation |
