"""Network output processor: curl, wget, httpie."""

import json
import re

from .base import Processor


class NetworkProcessor(Processor):
    priority = 30
    hook_patterns = [
        r"^(curl|wget|http|https)\b",
    ]

    @property
    def name(self) -> str:
        return "network"

    def can_handle(self, command: str) -> bool:
        # Match curl, wget, or httpie (http/https commands at start of line)
        # Avoid false positives: only match http/https as standalone commands, not as URLs
        return bool(
            re.search(r"\b(curl|wget)\b", command)
            or re.match(r"^\s*(http|https)\s+", command)
        )

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if re.search(r"\bcurl\b", command):
            return self._process_curl(output, command)
        if re.search(r"\bwget\b", command):
            return self._process_wget(output)
        if re.match(r"^\s*(http|https)\s+", command):
            return self._process_httpie(output)
        return output

    def _process_curl(self, output: str, command: str) -> str:
        lines = output.splitlines()

        is_verbose = re.search(r"\s-[a-zA-Z]*v|--verbose", command)
        if not is_verbose:
            # Non-verbose curl: strip progress meter, then try JSON compression
            stripped = self._strip_curl_progress(lines)
            return self._maybe_compress_json(stripped)

        # Verbose curl: strip TLS, connection, boilerplate headers
        result = []

        # Headers worth keeping in the response
        important_headers = {
            "content-type",
            "location",
            "www-authenticate",
            "set-cookie",
            "x-ratelimit",
            "retry-after",
            "authorization",
            "content-length",
            "transfer-encoding",
            "access-control-allow-origin",
            "x-request-id",
        }

        body_lines = []
        in_body = False

        for line in lines:
            stripped = line.strip()

            # TLS/SSL handshake noise
            if re.match(
                r"^\*\s*(SSL|TLS|ALPN|CAfile|CApath|Certificate|issuer|subject|"
                r"subjectAlt|Server certificate|Connected|Trying|"
                r"Connection(ed| #\d)| *expire| *start|"
                r"TCP_NODELAY|Mark bundle|upload completely|"
                r"Using Stream|old SSL|Closing|"
                r"successfully set certificate)\b",
                stripped,
            ):
                continue

            # Request headers (> prefix) -- keep only the method line
            if stripped.startswith("> "):
                header_content = stripped[2:].strip()
                if re.match(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+", header_content):
                    result.append(stripped)
                continue

            # Response headers (< prefix) -- filter
            if stripped.startswith("< "):
                header_content = stripped[2:].strip()
                # Status line: always keep
                if re.match(r"^HTTP/", header_content):
                    result.append(stripped)
                    continue
                # Empty header line marks end of headers, body starts
                if not header_content:
                    in_body = True
                    continue
                # Check if header is important
                header_lower = header_content.split(":")[0].lower() if ":" in header_content else ""
                if any(header_lower.startswith(h) for h in important_headers):
                    result.append(stripped)
                continue

            # Progress meter table (% Total % Received)
            if re.match(r"^\s+%\s+Total\s+%\s+Received", stripped):
                continue
            if re.match(r"^\s*\d+\s+\d+", stripped) and re.search(
                r"--:--:--|(\d+:){2}\d+", stripped
            ):
                continue

            # Info lines with * prefix -- keep only errors
            if stripped.startswith("* ") and not re.search(
                r"(error|fail|could not|refused)", stripped, re.I
            ):
                continue

            # Keep everything else (response body)
            if in_body:
                body_lines.append(line)
            else:
                result.append(line)

        # Try to compress body if it's JSON
        if body_lines:
            body_text = "\n".join(body_lines)
            compressed_body = self._maybe_compress_json(body_text)
            result.append(compressed_body)

        return "\n".join(result)

    def _strip_curl_progress(self, lines: list[str]) -> str:
        """Strip curl progress meter from non-verbose output."""
        result = []
        in_progress_table = False
        for line in lines:
            stripped = line.strip()
            # Progress table header
            if re.search(r"%\s+Total\s+%\s+Received", stripped):
                in_progress_table = True
                continue
            # Second header line (Dload/Upload columns)
            if in_progress_table and re.search(r"Dload\s+Upload", stripped):
                continue
            # Progress data lines (numbers with time patterns)
            if re.match(r"^\s*\d+\s+\d+", stripped) and re.search(
                r"--:--:--|(\d+:){2}\d+", stripped
            ):
                in_progress_table = False
                continue
            in_progress_table = False
            result.append(line)
        return "\n".join(result)

    def _maybe_compress_json(self, text: str) -> str:
        """If the text is a large JSON response, summarize its structure."""
        stripped = text.strip()
        if not stripped or (not stripped.startswith(("{", "["))):
            return text

        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return text

        # Only compress if the JSON is large
        if len(stripped) < 500:
            return text

        summary = self._summarize_json(data, depth=0, max_depth=2)
        return f"{summary}\n\n({len(stripped)} chars, {len(text.splitlines())} lines)"

    def _summarize_json(self, val, depth: int, max_depth: int) -> str:
        """Recursively summarize a JSON value."""
        indent = "  " * depth
        if isinstance(val, dict):
            if depth >= max_depth:
                return f"{{{len(val)} keys}}"
            items = []
            for k, v in val.items():
                summarized = self._summarize_json(v, depth + 1, max_depth)
                items.append(f'{indent}  "{k}": {summarized}')
            return "{\n" + ",\n".join(items) + f"\n{indent}}}"
        elif isinstance(val, list):
            if len(val) == 0:
                return "[]"
            if len(val) <= 2:
                inner = [self._summarize_json(v, depth + 1, max_depth) for v in val]
                return "[" + ", ".join(inner) + "]"
            first = self._summarize_json(val[0], depth + 1, max_depth)
            return f"[{first}, ... ({len(val)} items total)]"
        elif isinstance(val, str):
            if len(val) > 80:
                return f'"{val[:60]}..." ({len(val)} chars)'
            return json.dumps(val)
        else:
            return json.dumps(val)

    def _process_wget(self, output: str) -> str:
        lines = output.splitlines()
        result = []

        for line in lines:
            stripped = line.strip()

            # DNS resolution
            if re.match(r"^Resolving\s+", stripped):
                continue
            # Connection info
            if re.match(r"^Connecting to\s+", stripped):
                continue
            # Progress bars
            if re.search(r"\d+%\s*\[=*>?\s*\]", stripped):
                continue
            if re.match(r"^\s*\d+K\s+", stripped) and re.search(r"\.\.\.", stripped):
                continue
            # Length info (keep)
            if re.match(r"^Length:", stripped):
                result.append(stripped)
                continue
            # Saving to (keep)
            if re.match(r"^Saving to:", stripped):
                result.append(stripped)
                continue
            # Final status (keep)
            if re.search(r"saved|ERROR|error|failed|refused|not found", stripped, re.I):
                result.append(stripped)
                continue
            # HTTP response
            if re.match(r"^HTTP request sent", stripped) or re.search(r"^\d{3}\s", stripped):
                result.append(stripped)
                continue
            # Redirect
            if re.match(r"^Location:", stripped):
                result.append(stripped)
                continue

            result.append(line)

        return "\n".join(result)

    def _process_httpie(self, output: str) -> str:
        """Compress httpie output: keep status, important headers, compress body."""
        lines = output.splitlines()
        result = []
        body_lines = []
        in_body = False

        for line in lines:
            stripped = line.strip()

            # Status line: HTTP/1.1 200 OK
            if re.match(r"^HTTP/", stripped):
                result.append(line)
                continue

            # Headers (key: value format before body)
            if not in_body and re.match(r"^[\w-]+:", stripped):
                header_name = stripped.split(":")[0].lower()
                # Keep important headers
                important = {
                    "content-type", "location", "set-cookie", "www-authenticate",
                    "content-length", "x-request-id",
                }
                if any(header_name.startswith(h) for h in important):
                    result.append(line)
                continue

            # Empty line between headers and body
            if not in_body and not stripped:
                in_body = True
                continue

            if in_body:
                body_lines.append(line)

        # Compress body if JSON
        if body_lines:
            body_text = "\n".join(body_lines)
            compressed = self._maybe_compress_json(body_text)
            result.append(compressed)

        return "\n".join(result) if result else output
