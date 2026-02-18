#!/usr/bin/env python3
"""Wrapper CLI: executes a command and compresses its output.

Usage: python3 wrap.py '<command string>'

The command is passed as a single shell-quoted argument by hook_pretool.py.
This script executes it, compresses the combined output, and prints the result.

Flags:
    --dry-run  Show compression stats without replacing output.
"""

import logging
import os
import signal
import subprocess
import sys

# Ensure the extension root is importable (claude/ -> extension/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.engine import CompressionEngine
from src.tracker import SavingsTracker

# --- Debug logging (writes to ~/.token-saver/hook.log when TOKEN_SAVER_DEBUG=true) ---
_log = logging.getLogger("token-saver.wrap")
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


def main():
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print("Usage: python3 wrap.py '<command>'", file=sys.stderr)
        sys.exit(1)

    # The command comes as a single quoted argument from hook_pretool.py
    command_str = args[0] if len(args) == 1 else " ".join(args)
    _log.debug("Executing command: %r", command_str)

    timeout = config.get("wrap_timeout")

    # Forward SIGINT/SIGTERM to subprocess
    child_proc = None

    def signal_handler(signum, _frame):
        if child_proc and child_proc.poll() is None:
            child_proc.send_signal(signum)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Execute the original command
    try:
        child_proc = subprocess.Popen(  # noqa: S602
            command_str,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = child_proc.communicate(timeout=timeout)
        returncode = child_proc.returncode
    except subprocess.TimeoutExpired:
        if child_proc:
            child_proc.kill()
            child_proc.wait()
        print(f"[token-saver] Command timed out after {timeout}s: {command_str}", file=sys.stderr)
        sys.exit(124)
    except KeyboardInterrupt:
        if child_proc and child_proc.poll() is None:
            child_proc.kill()
            child_proc.wait()
        sys.exit(130)
    except OSError as e:
        print(f"[token-saver] Failed to execute: {e}", file=sys.stderr)
        sys.exit(127)
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

    # Combine stdout and stderr, keeping stderr separate for error context
    output = stdout or ""
    if stderr:
        output = (output + "\n" + stderr) if output else stderr

    if not output.strip():
        sys.exit(returncode)

    # Compress
    engine = CompressionEngine()
    compressed, processor_name, was_compressed = engine.compress(command_str, output)

    if dry_run:
        original_len = len(output)
        compressed_len = len(compressed)
        saved = original_len - compressed_len
        ratio = (saved / original_len * 100) if original_len > 0 else 0
        print(
            f"[token-saver dry-run] processor={processor_name} "
            f"original={original_len} compressed={compressed_len} "
            f"saved={saved} ({ratio:.1f}%)",
            file=sys.stderr,
        )
        print(output, end="")
        sys.exit(returncode)

    if was_compressed:
        _log.debug(
            "Compressed: processor=%s original=%d compressed=%d",
            processor_name,
            len(output),
            len(compressed),
        )
        try:
            tracker = SavingsTracker()
            tracker.record_saving(
                command=command_str,
                processor=processor_name,
                original_size=len(output),
                compressed_size=len(compressed),
                platform="claude_code",
            )
            tracker.close()
        except Exception:
            _log.exception("Tracking failed")
    else:
        _log.debug("Not compressed: processor=%s len=%d", processor_name, len(output))

    # Output the result (compressed or original)
    print(compressed, end="")
    sys.exit(returncode)


if __name__ == "__main__":
    main()
