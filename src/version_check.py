"""Check for new Token-Saver releases via GitHub API."""

import json
import urllib.request

from src import __version__

_GITHUB_API_URL = "https://api.github.com/repos/ppgranger/token-saver/releases/latest"


def _parse_version(version_str):
    """Parse 'X.Y.Z' or 'vX.Y.Z' into a tuple of ints.

    Pre-release suffixes (e.g. '1.0.0-beta') are stripped.
    """
    v = version_str.strip().lstrip("v")
    # Strip pre-release suffix: "1.0.0-beta.1" -> "1.0.0"
    v = v.split("-")[0]
    return tuple(int(x) for x in v.split("."))


def _fetch_latest_version(fetch_fn=None):
    """Fetch latest version string from GitHub API."""
    if fetch_fn is not None:
        return fetch_fn()

    req = urllib.request.Request(  # noqa: S310
        _GITHUB_API_URL,
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "token-saver"},
    )
    with urllib.request.urlopen(req, timeout=1) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    tag = data.get("tag_name", "")
    if not tag:
        raise ValueError("No tag_name in GitHub API response")
    return tag.lstrip("v")


def check_for_update(fetch_fn=None):
    """Check if a newer version of Token-Saver is available.

    Returns a notification string if an update is available, or None.
    Fully fail-open: any exception returns None.

    Args:
        fetch_fn: Override fetch function (for testing). Should return version string.
    """
    try:
        latest = _fetch_latest_version(fetch_fn)
        if _parse_version(latest) > _parse_version(__version__):
            return f"Update available: v{__version__} -> v{latest} -- Run: token-saver update"
    except Exception:
        return None

    return None
