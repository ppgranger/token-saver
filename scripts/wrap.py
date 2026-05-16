#!/usr/bin/env python3
"""Wrapper CLI: executes a command and compresses its output.

Usage: python3 wrap.py '<command string>'

The command is passed as a single shell-quoted argument by hook_pretool.py.
This script executes it, compresses the combined output, and prints the result.

For chained commands (&&, ;), each segment is compressed independently with
its own processor.  Marker echoes are injected between segments so the output
stream can be split back into per-segment chunks.

Flags:
    --dry-run  Show compression stats without replacing output.
"""

import logging
import os
import re
import signal
import subprocess
import sys
import uuid

# Ensure the extension root is importable (scripts/ -> plugin root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.chain_utils import extract_primary_command, split_chain_with_ops
from src.engine import CompressionEngine
from src.tracker import SavingsTracker

# --- Debug logging (writes to data_dir/hook.log when TOKEN_SAVER_DEBUG=true) ---
_log = logging.getLogger("token-saver.wrap")
_log.setLevel(logging.DEBUG)
_debug = os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes")
if _debug:
    from src import data_dir as _data_dir

    _log_dir = _data_dir()
    os.makedirs(_log_dir, exist_ok=True)
    _handler = logging.FileHandler(os.path.join(_log_dir, "hook.log"))
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
else:
    _log.addHandler(logging.NullHandler())


MARKER_PREFIX_TEMPLATE = "__TS_MARK_{}_"


def inject_markers(parts: list[tuple[str, str]], marker_prefix: str) -> str:
    """Build a rewritten command that emits `<marker_prefix><idx>` before each
    non-first segment.  Each marker+segment is wrapped in a brace group so the
    surrounding shell operator (`&&` / `;`) still applies to the user's segment.

    Example: parts=[(a,"&&"),(b,";"),(c,"")], prefix="M_"  ->
        a && { echo 'M_1'; b; } ; { echo 'M_2'; c; }
    """
    pieces: list[str] = []
    for i, (seg, op) in enumerate(parts):
        if i == 0:
            pieces.append(seg)
        else:
            # Single-quote the marker; markers contain only [A-Za-z0-9_] so safe.
            pieces.append(f"{{ echo '{marker_prefix}{i}'; {seg}; }}")
        if op:
            pieces.append(op)
    return " ".join(pieces)


def strip_markers(output: str, marker_prefix: str) -> str:
    """Remove marker lines from output (used for dry-run display)."""
    pattern = re.compile(r"^" + re.escape(marker_prefix) + r"\d+\s*\n?", re.MULTILINE)
    return pattern.sub("", output)


def split_output_by_markers(output: str, marker_prefix: str) -> list[tuple[int, str]]:
    """Split combined output into (segment_index, segment_output) chunks.

    The first chunk (before any marker) is always segment 0.  Subsequent
    chunks are indexed by the number embedded in their preceding marker.
    Markers may be missing if an `&&` short-circuited mid-chain; the
    embedded indices keep the mapping correct.
    """
    pattern = re.compile(r"^" + re.escape(marker_prefix) + r"(\d+)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(output))
    if not matches:
        return [(0, output)]

    chunks: list[tuple[int, str]] = []
    first_chunk = output[: matches[0].start()]
    # Strip the trailing newline that precedes the marker line.
    if first_chunk.endswith("\n"):
        first_chunk = first_chunk[:-1]
    chunks.append((0, first_chunk))

    for j, m in enumerate(matches):
        seg_idx = int(m.group(1))
        start = m.end()
        end = matches[j + 1].start() if j + 1 < len(matches) else len(output)
        body = output[start:end]
        if body.startswith("\n"):
            body = body[1:]
        if body.endswith("\n"):
            body = body[:-1]
        chunks.append((seg_idx, body))

    return chunks


def _run_command(
    command_str: str,
    timeout: int,
    merge_stderr: bool,
) -> tuple[str, str, int]:
    """Run command via shell, return (stdout, stderr, returncode).

    If merge_stderr is True, stderr is redirected into stdout (stderr returns "").
    Forwards SIGINT/SIGTERM to the child.
    """
    child_proc: subprocess.Popen | None = None

    def signal_handler(signum, _frame):
        if child_proc and child_proc.poll() is None:
            child_proc.send_signal(signum)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        child_proc = subprocess.Popen(  # noqa: S602
            command_str,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
        )
        stdout, stderr = child_proc.communicate(timeout=timeout)
        return stdout or "", stderr or "", child_proc.returncode
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


def _print_dry_run(
    processor_name: str, original_len: int, compressed_len: int, output: str
) -> None:
    saved = original_len - compressed_len
    ratio = (saved / original_len * 100) if original_len > 0 else 0
    chars_per_token = config.get("chars_per_token")
    orig_tokens = max(1, round(original_len / chars_per_token)) if original_len > 0 else 0
    comp_tokens = max(1, round(compressed_len / chars_per_token)) if compressed_len > 0 else 0
    saved_tokens = orig_tokens - comp_tokens
    print(
        f"[token-saver dry-run] processor={processor_name} "
        f"original={orig_tokens} tokens compressed={comp_tokens} tokens "
        f"saved={saved_tokens} tokens ({ratio:.1f}%)",
        file=sys.stderr,
    )
    print(output, end="")


def _record_saving(command: str, processor: str, original_len: int, compressed_len: int) -> None:
    try:
        tracker = SavingsTracker()
        _log.debug(
            "Recording: session=%s processor=%s original=%d compressed=%d",
            tracker.session_id,
            processor,
            original_len,
            compressed_len,
        )
        tracker.record_saving(
            command=command,
            processor=processor,
            original_size=original_len,
            compressed_size=compressed_len,
            platform="claude_code",
        )
        tracker.close()
    except Exception:
        _log.exception("Tracking failed")


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

    chain_parts = split_chain_with_ops(command_str)
    is_chain = len(chain_parts) > 1

    engine = CompressionEngine()

    if is_chain:
        marker_prefix = MARKER_PREFIX_TEMPLATE.format(uuid.uuid4().hex[:12])
        rewritten = inject_markers(chain_parts, marker_prefix)
        _log.debug("Chain rewrite: %r", rewritten)

        stdout, _stderr, returncode = _run_command(rewritten, timeout, merge_stderr=True)
        combined = stdout

        if not combined.strip():
            sys.exit(returncode)

        chunks = split_output_by_markers(combined, marker_prefix)

        compressed_parts: list[str] = []
        used_processors: list[str] = []
        total_original = 0
        total_compressed = 0

        for seg_idx, chunk_out in chunks:
            if seg_idx >= len(chain_parts):
                # Defensive: marker index out of range — pass through unchanged
                compressed_parts.append(chunk_out)
                total_original += len(chunk_out)
                total_compressed += len(chunk_out)
                continue
            seg_cmd = chain_parts[seg_idx][0]
            if not chunk_out:
                continue
            c_out, proc_name, _was = engine.compress(seg_cmd, chunk_out)
            compressed_parts.append(c_out)
            used_processors.append(proc_name)
            total_original += len(chunk_out)
            total_compressed += len(c_out)

        compressed = "\n".join(compressed_parts)

        # Summary processor label, e.g. "chain[git,git,git]"
        proc_label = "chain[" + ",".join(used_processors) + "]" if used_processors else "chain"

        if dry_run:
            display_output = strip_markers(combined, marker_prefix)
            _print_dry_run(proc_label, total_original, total_compressed, display_output)
            sys.exit(returncode)

        if total_compressed < total_original:
            _log.debug(
                "Chain compressed: processor=%s original=%d compressed=%d",
                proc_label,
                total_original,
                total_compressed,
            )
            _record_saving(command_str, proc_label, total_original, total_compressed)
        else:
            _log.debug("Chain not compressed: len=%d", total_original)

        print(compressed, end="")
        sys.exit(returncode)

    # --- Single-command path (unchanged behavior) ---
    stdout, stderr, returncode = _run_command(command_str, timeout, merge_stderr=False)
    output = stdout
    if stderr:
        output = (output + "\n" + stderr) if output else stderr

    if not output.strip():
        sys.exit(returncode)

    primary_cmd = extract_primary_command(command_str)
    compressed, processor_name, was_compressed = engine.compress(primary_cmd, output)

    if dry_run:
        _print_dry_run(processor_name, len(output), len(compressed), output)
        sys.exit(returncode)

    if was_compressed:
        _log.debug(
            "Compressed: processor=%s original=%d compressed=%d",
            processor_name,
            len(output),
            len(compressed),
        )
        _record_saving(command_str, processor_name, len(output), len(compressed))
    else:
        _log.debug("Not compressed: processor=%s len=%d", processor_name, len(output))

    print(compressed, end="")
    sys.exit(returncode)


if __name__ == "__main__":
    main()
