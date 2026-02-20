# Network Processor

**File:** `src/processors/network.py` | **Priority:** 30 | **Name:** `network`

Handles HTTP client output.

## Supported Commands

curl, wget, http (httpie), https (httpie).

## Strategy

| Command | Strategy |
|---|---|
| `curl -v` | Strips TLS handshake (`*` lines), connection lifecycle, boilerplate response headers (Date, Server, X-Powered-By, etc.). Keeps HTTP status, request method, essential headers (Content-Type, Location, Set-Cookie, X-Request-Id, Authorization). JSON response bodies > 500 chars are summarized by structure |
| `curl` (non-verbose) | Strips progress meter table. JSON bodies are summarized if large |
| `wget` | Strips DNS resolution, connection info, progress bars. Keeps HTTP status, Length, save location, final result |
| `http`/`https` (httpie) | Keeps status line, important headers (Content-Type, Location, Set-Cookie, Authorization, X-Request-Id). Strips Date, Server, X-Powered-By. JSON bodies are summarized if large |

## JSON Response Compression

When the output (or body portion) is valid JSON and exceeds 500 characters, the processor summarizes it:
- Objects: shows keys and value types
- Arrays: shows length and first element structure
- Long strings: truncated with char count

## False Positive Prevention

The processor uses `re.match(r"^\s*(http|https)\s+", command)` for httpie to avoid false-matching commands that merely contain `http`/`https` as part of URLs (e.g., `git push https://...`).
