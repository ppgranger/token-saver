#!/usr/bin/env python3
"""PreToolUse hook for Claude Code.

Handles two optimizations:
1. Bash commands: rewrites compressible commands to go through wrap.py for output compression.
2. Read tool (images): resizes large images before Claude reads them to save visual tokens.

Uses shlex.quote() to prevent shell injection when rewriting Bash commands.
"""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# --- Debug logging (writes to ~/.token-saver/hook.log when TOKEN_SAVER_DEBUG=true) ---
_log = logging.getLogger("token-saver.hook_pretool")
_log.setLevel(logging.DEBUG)
_debug = os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes")
if _debug:
    _log_dir = os.path.join(os.path.expanduser("~"), ".token-saver")
    os.makedirs(_log_dir, exist_ok=True)
    _handler = logging.FileHandler(os.path.join(_log_dir, "hook.log"))
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
else:
    _log.addHandler(logging.NullHandler())


# Build patterns from processor registry (auto-discovered)
def _load_compressible_patterns() -> list[str]:
    """Import hook_patterns from the processor registry."""
    # Add extension root to path so we can import the src package
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _extension_root = os.path.dirname(_this_dir)
    _log.debug("this_dir=%s, extension_root=%s", _this_dir, _extension_root)
    if _extension_root not in sys.path:
        sys.path.insert(0, _extension_root)
    from src.processors import collect_hook_patterns  # noqa: PLC0415

    patterns = collect_hook_patterns()
    _log.debug("Loaded %d compressible patterns", len(patterns))
    return patterns


try:
    COMPRESSIBLE_PATTERNS = _load_compressible_patterns()
except Exception:
    _log.exception("Failed to load compressible patterns")
    raise
COMPILED_PATTERNS = [re.compile(p) for p in COMPRESSIBLE_PATTERNS]

# Commands that should NEVER be wrapped
# We check these on the raw command string (before splitting)
EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # unquoted pipe
    r"(?<!['\"])&&(?!['\"])",  # unquoted &&
    r"(?<!['\"])\|\|(?!['\"])",  # unquoted ||
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*(ssh|scp|rsync)\b",
    r"token.saver",  # avoid wrapping ourselves
    r"wrap\.py",
    r">\s",  # redirections
    r"<\(",  # process substitution
    r"^\s*sudo\b",  # never wrap sudo
    r"^\s*env\s+\S+=",  # env VAR=val prefix — too complex to wrap
]

COMPILED_EXCLUDED = [re.compile(p) for p in EXCLUDED_PATTERNS]


def is_compressible(command: str) -> bool:
    """Check if a command should be compressed."""
    cmd = command.strip()
    if not cmd:
        return False
    for pattern in COMPILED_EXCLUDED:
        if pattern.search(cmd):
            return False
    return any(pattern.search(cmd) for pattern in COMPILED_PATTERNS)


# Image file extensions that Claude processes as visual tokens
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Max useful resolution for Claude Vision (beyond this, Claude downscales anyway)
_MAX_IMAGE_DIMENSION = 1568


def _optimize_image(file_path: str) -> str | None:
    """Resize large images before Claude reads them to save visual tokens.

    Claude's vision API charges tokens = (width * height) / 750.
    Beyond 1568px, Claude auto-downscales anyway — so resizing beforehand
    saves tokens without quality loss.

    Uses macOS sips (built-in) or ImageMagick identify+convert as fallback.
    Returns path to optimized temp file, or None if no optimization needed.
    """
    if not os.path.isfile(file_path):
        return None

    # Get current dimensions
    width, height = _get_image_dimensions(file_path)
    if width is None or height is None:
        return None

    # Skip if already within limits
    if width <= _MAX_IMAGE_DIMENSION and height <= _MAX_IMAGE_DIMENSION:
        _log.debug("Image %s already within limits (%dx%d)", file_path, width, height)
        return None

    # Resize to temp file
    ext = os.path.splitext(file_path)[1].lower()
    out_ext = ".jpeg" if ext not in (".png",) else ext
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=out_ext, prefix="token-saver-img-")
    os.close(tmp_fd)

    try:
        if _has_sips():
            # macOS: sips -Z resizes to fit within max dimension, preserving aspect ratio
            cmd = ["sips", "-Z", str(_MAX_IMAGE_DIMENSION), file_path, "--out", tmp_path]
            if out_ext == ".jpeg":
                cmd.extend(["-s", "format", "jpeg", "-s", "formatOptions", "80"])
            subprocess.run(cmd, capture_output=True, check=False, timeout=10)  # noqa: S603
        elif _has_imagemagick():
            # Linux/other: ImageMagick convert
            geometry = f"{_MAX_IMAGE_DIMENSION}x{_MAX_IMAGE_DIMENSION}>"
            cmd = ["convert", file_path, "-resize", geometry, "-quality", "80", tmp_path]
            subprocess.run(cmd, capture_output=True, check=False, timeout=10)  # noqa: S603
        else:
            _log.debug("No image tool available (sips or ImageMagick)")
            os.unlink(tmp_path)
            return None

        # Verify the output file was created and is valid
        if os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
            _log.debug(
                "Optimized image: %s (%dx%d) -> %s",
                file_path,
                width,
                height,
                tmp_path,
            )
            return tmp_path
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log.debug("Image optimization failed: %s", exc)

    # Cleanup on failure
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    return None


def _get_image_dimensions(file_path: str) -> tuple[int | None, int | None]:
    """Get image width and height using available system tools."""
    try:
        if _has_sips():
            result = subprocess.run(  # noqa: S603
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", file_path],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            width = height = None
            for line in result.stdout.splitlines():
                if "pixelWidth" in line:
                    width = int(line.split(":")[-1].strip())
                elif "pixelHeight" in line:
                    height = int(line.split(":")[-1].strip())
            return width, height
        if _has_imagemagick():
            result = subprocess.run(  # noqa: S603
                ["identify", "-format", "%w %h", file_path],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        _log.debug("Failed to get image dimensions: %s", exc)
    return None, None


def _has_sips() -> bool:
    """Check if sips (macOS) is available."""
    if not hasattr(_has_sips, "_cached"):
        _has_sips._cached = shutil.which("sips") is not None  # type: ignore[attr-defined]
    return _has_sips._cached  # type: ignore[attr-defined]


def _has_imagemagick() -> bool:
    """Check if ImageMagick identify is available."""
    if not hasattr(_has_imagemagick, "_cached"):
        _has_imagemagick._cached = shutil.which("identify") is not None  # type: ignore[attr-defined]
    return _has_imagemagick._cached  # type: ignore[attr-defined]


def main():
    try:
        raw_input = sys.stdin.read()
        _log.debug("stdin: %s", raw_input[:500])
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError) as exc:
        _log.debug("Invalid JSON input: %s", exc)
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # --- Image optimization: intercept Read tool on large image files ---
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path and file_path.lower().endswith(_IMAGE_EXTENSIONS):
            optimized_path = _optimize_image(file_path)
            if optimized_path:
                result = {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "updatedInput": {"file_path": optimized_path},
                    },
                }
                json.dump(result, sys.stdout)
        sys.exit(0)

    # --- Bash command compression ---
    if tool_name != "Bash":
        _log.debug("Skipping tool: %s", tool_name)
        sys.exit(0)

    command = tool_input.get("command", "")

    if not command or not is_compressible(command):
        _log.debug("Not compressible: %r", command[:200])
        sys.exit(0)

    # Build path to wrap.py (same directory)
    wrap_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrap.py")
    if not os.path.isfile(wrap_py):
        _log.warning("wrap.py not found at %s", wrap_py)
        sys.exit(0)  # Fail open — don't break the command

    # Rewrite: pass the original command as a single quoted argument to avoid injection
    new_command = f"python3 {shlex.quote(wrap_py)} {shlex.quote(command)}"
    _log.debug("Rewriting: %r -> %r", command, new_command)

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {"command": new_command},
        },
    }

    json.dump(result, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
