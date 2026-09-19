# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deterministic, best-effort secret masking for opt-in Delta captures.

This recognizes credential assignments, authorization headers, URL passwords,
common token formats and PEM private keys. It is not a general secret detector:
unlabeled passwords, custom encodings and unfamiliar formats may remain. Callers
must sanitize before parsing, comparing or retaining output, and must never
restore original text after this step.
"""

import re

_MASK = "***"
_ASSIGNMENT = re.compile(
    r"(?<![\w.-])(?P<key>[A-Za-z_][A-Za-z0-9_.-]{0,127})"
    r"(?P<quote>\\?[\"'])?"
    r"(?:[ \t]*:[ \t]*(?:str|bytes)(?:[ \t]*\|[ \t]*None)?"
    r"(?=[ \t]*=))?[ \t]*(?P<operator>[:=])(?![:=])[ \t]*"
)
_SECRET_NAME = re.compile(
    r"(?:^|[_.-])(?:password|passwd|passphrase|token|api_?key|secret|"
    r"authorization|access_?key|private_?key|credentials?)(?:$|[_.-])",
    re.IGNORECASE,
)
_AUTH_SCHEME = re.compile(r"(?:Bearer|Basic)[ \t]+", re.IGNORECASE)
_URL_PASSWORD = re.compile(
    r"(?P<prefix>[A-Za-z][A-Za-z0-9+.-]{0,31}://[^\s/@:]*:)"
    r"[^\s/@]*@"
)
_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|"
    r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r")(?![A-Za-z0-9_-])"
)
_PRIVATE_KEY = re.compile(
    r"(?P<begin>-----BEGIN (?P<kind>(?:[A-Z0-9]+ )?PRIVATE KEY)-----)"
    r"(?P<body>.*?)(?P<end>-----END (?P=kind)-----|\Z)",
    re.DOTALL,
)
_NON_NEWLINE = re.compile(r"[^\r\n]+")
_BARE_VALUE = re.compile(r"[^\s,;\]\[{}()\"']+")
_SOURCE_PREFIX = re.compile(r"(?i:[bruf]{1,2})(?=[\"'])")
_ENV_ASSIGNMENT = re.compile(
    r"[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=[ \t]*"
)


def _mask_private_key(match: re.Match[str]) -> str:
    """Retain PEM delimiters and line endings while removing its body."""
    body = _NON_NEWLINE.sub(_MASK, match.group("body"))
    return match.group("begin") + body + match.group("end")


def _quoted_end(text: str, start: int, quote: str) -> int:
    """Find a closing quote without interpreting the quoted value.

    A delimiter escaped by one backslash handles JSON printed inside a string.
    Escape runs distinguish a quoted character from an escaped delimiter.
    An unterminated value is
    masked through its current physical line; triple-quoted literals may span
    lines and are masked through the end of the input when unterminated.
    """
    index = start
    while index < len(text) and (len(quote) == 3 or text[index] not in "\r\n"):
        if text[index] == "\\":
            end = index + 1
            while end < len(text) and text[end] == "\\":
                end += 1
            if quote.startswith("\\"):
                if (end - index) % 4 == 1 and text.startswith(quote[1:], end):
                    return end - 1
                index = end
                if index < len(text) and text[index] not in "\r\n":
                    index += 1
            else:
                escaped = (end - index) % 2
                index = end
                if escaped and index < len(text) and text[index] not in "\r\n":
                    index += 1
            continue
        if text.startswith(quote, index):
            return index
        index += 1
    return index


def _value_span(text: str, start: int) -> tuple[int, int, bool]:
    """Return a value's content bounds and whether quotes surround it."""
    quote = ""
    prefix = _SOURCE_PREFIX.match(text, start)
    if prefix:
        start = prefix.end()
    if text.startswith(('"""', "'''"), start):
        quote = text[start : start + 3]
    elif text.startswith(('\\"', "\\'"), start):
        quote = text[start : start + 2]
    elif text.startswith(('"', "'"), start):
        quote = text[start]
    if quote:
        start += len(quote)
        return start, _quoted_end(text, start, quote), True
    value = _BARE_VALUE.match(text, start)
    return start, value.end() if value else start, False


def _bare_end(text: str, match: re.Match[str], start: int, end: int) -> int:
    """Respect complete environment values and URL query delimiters.

    Environment output does not quote punctuation or spaces in values, so an
    assignment occupying a physical line must mask the entire value. Query
    parameters have explicit delimiters, and source literals retain their
    surrounding syntax through the ordinary value parser.
    """
    line_start = (
        max(
            text.rfind("\n", 0, match.start()),
            text.rfind("\r", 0, match.start()),
        )
        + 1
    )
    if _ENV_ASSIGNMENT.fullmatch(text[line_start : match.end()]):
        tail = _NON_NEWLINE.match(text, start)
        return tail.end() if tail else start
    if match.start() > 0 and text[match.start() - 1] in "?&":
        for delimiter in "&#":
            position = text.find(delimiter, start, end)
            if position != -1:
                end = position
    return end


def _mask_assignments(text: str) -> str:
    """Mask recognized values while retaining adjacent diagnostic content."""
    parts = []
    cursor = 0
    for match in _ASSIGNMENT.finditer(text):
        if match.start() < cursor or not _SECRET_NAME.search(match["key"]):
            continue
        start = match.end()
        if "authorization" in match["key"].lower():
            scheme = _AUTH_SCHEME.match(text, start)
            if scheme:
                start = scheme.end()
        start, end, quoted = _value_span(text, start)
        if not quoted:
            end = _bare_end(text, match, start, end)
        if start == end:
            continue
        replacement = _NON_NEWLINE.sub(_MASK, text[start:end])
        if not quoted and match["quote"] and match["operator"] == ":":
            # Keep JSON or dictionary syntax valid when the value was numeric.
            replacement = match["quote"] + _MASK + match["quote"]
        parts.append(text[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def sanitize(text: str) -> str:
    """Mask recognized secrets without disk, configuration or network access.

    Assignment keys are ASCII identifiers up to 128 characters, with credential
    words separated by underscores, dots or hyphens. Quoted values support
    ordinary escapes and JSON escaped once inside another string. Value lengths
    are unrestricted; CR/LF sequences and surrounding diagnostic lines survive.
    Unquoted environment assignment lines mask the entire remaining value,
    including spaces and punctuation; URL queries retain parameter delimiters.
    Truncated ordinary quoted values are masked through their line; truncated
    triple-quoted literals and PEM blocks through the remaining input.
    Repeated calls produce the same result.

    This heuristic intentionally has no allowlist and cannot guarantee removal
    of arbitrary secrets. Capture-size and retention limits belong to callers.

    Args:
        text: Captured command output, or previously sanitized output.

    Returns:
        Text with recognized credential values replaced by ``***``. Unrecognized
        text is unchanged; source text is never read from another location.
    """
    text = _PRIVATE_KEY.sub(_mask_private_key, text)
    text = _mask_assignments(text)
    text = _URL_PASSWORD.sub(lambda match: match["prefix"] + _MASK + "@", text)
    return _TOKEN.sub(_MASK, text)
