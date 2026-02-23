"""Utilities for splitting and analysing chained shell commands (&&, ;)."""

import re

# Matches unquoted && or ; for detection purposes only (use split_chain()
# for actual splitting, which respects quoted strings).
CHAIN_SPLIT_RE = re.compile(r"(?<!['\"])(?:&&|;)(?!['\"])")

# Commands that produce no stdout on success and are safe to ignore
# when determining the "primary" command in a chain.
SILENT_CMDS_RE = re.compile(
    r"^\s*(?:"
    r"cd|pushd|popd"
    r"|mkdir(?:\s+-p)?"
    r"|cp|mv|rm"
    r"|touch|chmod|chown|ln"
    r"|export|unset|source"
    r"|set|shopt|alias|hash|type"
    r"|true|false"
    r"|git\s+(?:add|rm|checkout|switch|reset|clean|config|init|tag|commit|mv|restore)"
    r")(?:\s|$)"
)


def split_chain(command: str) -> list[str]:
    """Split a command string on unquoted ``&&`` and ``;`` into segments.

    Respects single- and double-quoted strings so that e.g.
    ``git commit -m "fix; done"`` is NOT split on the ``;``.
    """
    segments: list[str] = []
    current: list[str] = []
    i = 0
    n = len(command)

    while i < n:
        ch = command[i]

        # Skip over quoted strings
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            while i < n and command[i] != quote:
                current.append(command[i])
                i += 1
            if i < n:
                current.append(command[i])  # closing quote
                i += 1
            continue

        # Check for &&
        if ch == "&" and i + 1 < n and command[i + 1] == "&":
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 2
            continue

        # Check for ;
        if ch == ";":
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    seg = "".join(current).strip()
    if seg:
        segments.append(seg)

    return segments


def extract_primary_command(command: str) -> str:
    """Return the last non-silent segment of a (possibly chained) command.

    If no non-silent segment is found, return the last segment.
    """
    segments = split_chain(command)
    if not segments:
        return command

    # Walk backwards to find the last non-silent segment
    for seg in reversed(segments):
        if not SILENT_CMDS_RE.match(seg):
            return seg

    # All segments are silent — return the last one
    return segments[-1]
