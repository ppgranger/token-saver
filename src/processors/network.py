"""Network output processor: curl, wget, httpie."""

import re

from .base import Processor


class NetworkProcessor(Processor):
    priority = 30
    hook_patterns = [
        r"^(curl|wget)\b",
    ]

    @property
    def name(self) -> str:
        return "network"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\b(curl|wget|http|https)\b", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if re.search(r"\bcurl\b", command):
            return self._process_curl(output, command)
        if re.search(r"\bwget\b", command):
            return self._process_wget(output)
        return output

    def _process_curl(self, output: str, command: str) -> str:
        lines = output.splitlines()

        is_verbose = re.search(r"\s-[a-zA-Z]*v|--verbose", command)
        if not is_verbose:
            # Non-verbose curl: just strip progress meter
            return self._strip_curl_progress(lines)

        # Verbose curl: strip TLS, connection, boilerplate headers
        result = []
        _status_line = ""
        _kept_headers = []

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

            # Request headers (> prefix) — keep only the method line
            if stripped.startswith("> "):
                header_content = stripped[2:].strip()
                if re.match(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+", header_content):
                    result.append(stripped)
                continue

            # Response headers (< prefix) — filter
            if stripped.startswith("< "):
                header_content = stripped[2:].strip()
                # Status line: always keep
                if re.match(r"^HTTP/", header_content):
                    _status_line = header_content
                    result.append(stripped)
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

            # Info lines with * prefix — keep only errors
            if stripped.startswith("* ") and not re.search(
                r"(error|fail|could not|refused)", stripped, re.I
            ):
                continue

            # Keep everything else (response body)
            result.append(line)

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
