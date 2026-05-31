"""Check for new Token-Saver releases via GitHub API."""

import json
import os
import time
import urllib.request

from src import __version__

_GITHUB_API_URL = "https://api.github.com/repos/ppgranger/token-saver/releases/latest"

# Cache the remote version lookup so the SessionStart hook doesn't hit GitHub
# on every new session (which both adds latency and risks rate-limiting).
_CACHE_TTL_SECONDS = 86400  # 24h


def _cache_path():
    from src import data_dir  # noqa: PLC0415

    return os.path.join(data_dir(), ".version_check_cache")


def _read_cache(ttl):
    """Return the cached latest-version string if still fresh, else None."""
    try:
        with open(_cache_path()) as f:
            data = json.load(f)
        if time.time() - float(data["checked_at"]) < ttl:
            return data["latest"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


def _write_cache(latest):
    """Persist the latest-version lookup with a timestamp (best-effort)."""
    try:
        path = _cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"latest": latest, "checked_at": time.time()}, f)
    except OSError:
        pass


def _parse_version(version_str):
    """Parse 'X.Y.Z' or 'vX.Y.Z' into a tuple of ints.

    Pre-release suffixes (e.g. '1.0.0-beta') are stripped.
    """
    v = version_str.strip().lstrip("v")
    # Strip pre-release suffix: "1.0.0-beta.1" -> "1.0.0"
    v = v.split("-")[0]
    return tuple(int(x) for x in v.split("."))


def _fetch_latest_version(fetch_fn=None, timeout=1):
    """Fetch latest version string from GitHub API.

    Args:
        fetch_fn: Override fetch function (for testing). Should return version string.
        timeout: HTTP timeout in seconds (default 1s for hooks, use higher for CLI).
    """
    if fetch_fn is not None:
        return fetch_fn()

    req = urllib.request.Request(  # noqa: S310
        _GITHUB_API_URL,
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "token-saver"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    tag = data.get("tag_name", "")
    if not tag:
        raise ValueError("No tag_name in GitHub API response")
    return tag.lstrip("v")


def check_for_update(fetch_fn=None, cache_ttl=_CACHE_TTL_SECONDS):
    """Check if a newer version of Token-Saver is available.

    Returns a notification string if an update is available, or None.
    Fully fail-open: any exception returns None.

    The remote lookup is cached for ``cache_ttl`` seconds so repeated
    SessionStart hooks reuse a recent result instead of re-querying GitHub.
    When ``fetch_fn`` is supplied (tests) the cache is bypassed entirely.

    Args:
        fetch_fn: Override fetch function (for testing). Should return version string.
        cache_ttl: Seconds a cached lookup stays valid (0 disables the cache).
    """
    try:
        if fetch_fn is not None:
            latest = _fetch_latest_version(fetch_fn)
        else:
            latest = _read_cache(cache_ttl) if cache_ttl > 0 else None
            if latest is None:
                latest = _fetch_latest_version()
                if cache_ttl > 0:
                    _write_cache(latest)
        if _parse_version(latest) > _parse_version(__version__):
            return f"Update available: v{__version__} -> v{latest} -- Run: token-saver update"
    except Exception:
        return None

    return None
