#!/usr/bin/env python3
"""Wrapper CLI: executes a command and compresses its output.

Usage: python3 wrap.py '<command string>'

The command is passed as a single shell-quoted argument by hook_pretool.py.
This script executes it, compresses the combined output, and prints the result.

For chained commands (&&, ;), each segment is compressed independently with
its own processor.  Marker echoes are injected between segments so the output
stream can be split back into per-segment chunks.

Flags:
    --dry-run       Show compression stats without replacing output.
    --show-removed  With --dry-run, also print a line/byte breakdown of what
                    compression removed (to stderr).
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

from src import config, core
from src.chain_utils import extract_primary_command, split_chain_with_ops
from src.diffstat import format_summary, summarize
from src.engine import CompressionEngine

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

# Audit logging + savings/mismatch recording live in src.core, shared with the
# Gemini hook.  Platform is always claude_code here.
_PLATFORM = "claude_code"


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
        # The child runs in its own session (start_new_session below), so the
        # terminal delivers Ctrl-C only to us, not to the child.  Forwarding
        # here is therefore the child's *only* signal — no double-delivery.
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
            start_new_session=True,
        )
        stdout, stderr = child_proc.communicate(timeout=timeout)
        return stdout or "", stderr or "", child_proc.returncode
    except subprocess.TimeoutExpired:
        # Fail open: kill the child but keep whatever it buffered so far, so a
        # slow/streaming command still returns (compressed) partial output
        # instead of losing everything.
        partial_out, partial_err = "", ""
        if child_proc:
            child_proc.kill()
            try:
                partial_out, partial_err = child_proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                partial_out, partial_err = "", ""
        note = f"[token-saver] Command timed out after {timeout}s (partial output shown)"
        print(note, file=sys.stderr)
        partial_out = (partial_out or "") + f"\n{note}\n"
        return partial_out, partial_err or "", 124
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


def _cap_output(output: str) -> str:
    """Hard-cap output length to ``max_output_bytes`` chars, noting truncation.

    Pathological commands can emit hundreds of MB; without a cap the whole
    payload flows into the compression engine and is held in memory.  We keep
    the first N chars (where the useful head usually lives) and append a note.
    A value <= 0 disables the cap.
    """
    cap = config.get("max_output_bytes")
    if not cap or cap <= 0 or len(output) <= cap:
        return output
    note = f"\n[token-saver] Output truncated at {cap:,} chars (was {len(output):,})\n"
    return output[:cap] + note


def _print_dry_run(
    processor_name: str,
    original_len: int,
    compressed_len: int,
    output: str,
    diff_summary: dict | None = None,
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
    if diff_summary is not None:
        print(format_summary(diff_summary), file=sys.stderr)
    print(output, end="")


def main():
    dry_run = "--dry-run" in sys.argv
    show_removed = "--show-removed" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--dry-run", "--show-removed")]

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
        combined = _cap_output(stdout)

        if not combined.strip():
            sys.exit(returncode)

        chunks = split_output_by_markers(combined, marker_prefix)

        compressed_parts: list[str] = []
        used_processors: list[str] = []
        mismatches: list[tuple[str, str, int]] = []
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
            try:
                c_out, proc_name, _was = engine.compress(seg_cmd, chunk_out)
                if engine.last_event.get("is_mismatch"):
                    mismatches.append(
                        (seg_cmd, engine.last_event["attempted_processor"], len(chunk_out))
                    )
            except Exception:
                _log.exception("Compression failed for segment %r — passing through", seg_cmd)
                c_out, proc_name = chunk_out, "passthrough"
            compressed_parts.append(c_out)
            used_processors.append(proc_name)
            total_original += len(chunk_out)
            total_compressed += len(c_out)

        compressed = "\n".join(compressed_parts)

        # Summary processor label, e.g. "chain[git,git,git]"
        proc_label = "chain[" + ",".join(used_processors) + "]" if used_processors else "chain"

        if dry_run:
            display_output = strip_markers(combined, marker_prefix)
            diff_summary = summarize(display_output, compressed) if show_removed else None
            _print_dry_run(
                proc_label, total_original, total_compressed, display_output, diff_summary
            )
            sys.exit(returncode)

        core.audit_log(command_str, proc_label, total_original, total_compressed)
        core.record_mismatches(mismatches, _PLATFORM)

        if total_compressed < total_original:
            _log.debug(
                "Chain compressed: processor=%s original=%d compressed=%d",
                proc_label,
                total_original,
                total_compressed,
            )
            core.record_saving(
                command_str, proc_label, total_original, total_compressed, _PLATFORM
            )
        else:
            _log.debug("Chain not compressed: len=%d", total_original)

        print(compressed, end="")
        sys.exit(returncode)

    # --- Single-command path (unchanged behavior) ---
    stdout, stderr, returncode = _run_command(command_str, timeout, merge_stderr=False)
    output = stdout
    if stderr:
        output = (output + "\n" + stderr) if output else stderr
    output = _cap_output(output)

    if not output.strip():
        sys.exit(returncode)

    primary_cmd = extract_primary_command(command_str)
    result = core.compress(primary_cmd, output, engine=engine)

    if dry_run:
        diff_summary = summarize(output, result.compressed) if show_removed else None
        _print_dry_run(
            result.processor, len(output), len(result.compressed), output, diff_summary
        )
        sys.exit(returncode)

    # Savings are attributed to the full command string (not just the primary)
    # so stats group by what the user actually typed.
    core.audit_log(primary_cmd, result.processor, result.original_len, result.compressed_len)
    if result.is_mismatch:
        core.record_mismatches(
            [(primary_cmd, result.attempted_processor, result.original_len)], _PLATFORM
        )
    if result.was_compressed:
        _log.debug(
            "Compressed: processor=%s original=%d compressed=%d",
            result.processor,
            result.original_len,
            result.compressed_len,
        )
        core.record_saving(
            command_str, result.processor, result.original_len, result.compressed_len, _PLATFORM
        )
    else:
        _log.debug("Not compressed: processor=%s len=%d", result.processor, result.original_len)

    print(result.compressed, end="")
    sys.exit(returncode)


if __name__ == "__main__":
    main()
