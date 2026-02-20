"""Git output processor: status, diff, log, show, push/pull/fetch, reflog, branch, blame."""

import re

from .. import config
from .base import Processor

# Optional git global options that may appear between 'git' and the subcommand.
# Covers: -C <path>, --no-pager, -c <key>=<val>, --git-dir <path>, --work-tree <path>
_GIT_OPTS = (
    r"(?:-C\s+\S+\s+|--no-pager\s+|-c\s+\S+\s+"
    r"|--git-dir(?:=|\s+)\S+\s+|--work-tree(?:=|\s+)\S+\s+)*"
)

_GIT_SUBCMDS = (
    r"(status|diff|log|show|push|pull|fetch|clone|branch|stash|reflog|remote"
    r"|blame|cherry-pick|rebase|merge)"
)
_GIT_CMD_RE = re.compile(rf"\bgit\s+{_GIT_OPTS}{_GIT_SUBCMDS}\b")


class GitProcessor(Processor):
    priority = 20
    hook_patterns = [
        rf"^git\s+{_GIT_OPTS}(status|diff|log|show|push|pull|fetch|clone|branch|stash|reflog|remote|blame|cherry-pick|rebase|merge)\b",
    ]

    @property
    def name(self) -> str:
        return "git"

    def can_handle(self, command: str) -> bool:
        return bool(_GIT_CMD_RE.search(command))

    def _get_subcmd(self, command: str) -> str | None:
        """Extract the git subcommand, skipping any global options."""
        m = _GIT_CMD_RE.search(command)
        return m.group(1) if m else None

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output
        subcmd = self._get_subcmd(command)
        if subcmd == "status":
            return self._process_status(output)
        if subcmd == "diff":
            return self._process_diff(output, command)
        if subcmd == "log":
            return self._process_log(output, command)
        if subcmd == "show":
            return self._process_show(output)
        if subcmd in ("push", "pull", "fetch", "clone"):
            return self._process_transfer(output)
        if subcmd == "branch":
            return self._process_branch(output)
        if subcmd == "stash":
            if re.search(r"\bstash\s+list\b", command):
                return self._process_stash_list(output)
            return output
        if subcmd == "reflog":
            return self._process_reflog(output)
        if subcmd == "blame":
            return self._process_blame(output)
        if subcmd in ("cherry-pick", "rebase", "merge"):
            return self._process_transfer(output)
        return output

    def _process_status(self, output: str) -> str:
        lines = output.strip().splitlines()
        counts: dict[str, int] = {}
        files_by_dir: dict[str, list[str]] = {}
        header_lines = []
        in_untracked = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Header lines
            if stripped.startswith(("On branch", "Your branch", "HEAD detached")):
                header_lines.append(stripped)
                in_untracked = False
                continue
            if stripped.startswith(("nothing to commit", "no changes added")):
                header_lines.append(stripped)
                in_untracked = False
                continue

            # Section headers
            if stripped.startswith("Untracked files:"):
                in_untracked = True
                continue
            if stripped.startswith(("Changes", "Unmerged")):
                in_untracked = False
                continue
            # Skip hint lines
            if stripped.startswith("("):
                continue

            # Parse long-format verbose status
            if stripped.startswith("modified:"):
                code, filepath = "M", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("new file:"):
                code, filepath = "A", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("deleted:"):
                code, filepath = "D", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("renamed:"):
                code, filepath = "R", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("copied:"):
                code, filepath = "C", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("both modified:"):
                code, filepath = "UU", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("both added:"):
                code, filepath = "AA", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("both deleted:"):
                code, filepath = "DD", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("added by us:"):
                code, filepath = "AU", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("added by them:"):
                code, filepath = "UA", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("deleted by us:"):
                code, filepath = "DU", stripped.split(":", 1)[1].strip()
            elif stripped.startswith("deleted by them:"):
                code, filepath = "UD", stripped.split(":", 1)[1].strip()
            # Parse short-format status: XY filename
            # Supports all status codes: M, A, D, R, C, U, ?, !
            elif re.match(r"^([MADRCTU?! ]{1,2})\s+(.+)$", stripped):
                m = re.match(r"^([MADRCTU?! ]{1,2})\s+(.+)$", stripped)
                code_raw = m.group(1).strip()
                filepath = m.group(2).strip().strip('"')
                code = code_raw[0] if code_raw[0] != " " else code_raw[-1]
            # Untracked files section: just bare filenames (tab-indented in raw output)
            elif in_untracked and not stripped.startswith("("):
                code, filepath = "?", stripped
            else:
                continue

            counts[code] = counts.get(code, 0) + 1
            parts = filepath.rsplit("/", 1)
            dir_name = parts[0] if len(parts) > 1 else "."
            file_name = parts[-1]
            files_by_dir.setdefault(dir_name, []).append(f"{code} {file_name}")

        result = []
        if header_lines:
            result.append(" | ".join(header_lines))

        summary_parts = [f"{k}:{v}" for k, v in sorted(counts.items()) if v > 0]
        if summary_parts:
            total = sum(counts.values())
            result.append(f"Files: {total} ({', '.join(summary_parts)})")

        for dir_name, files in sorted(files_by_dir.items()):
            if len(files) > 8:
                codes = {}
                for f in files:
                    c = f.split(" ", 1)[0]
                    codes[c] = codes.get(c, 0) + 1
                desc = ", ".join(f"{c}:{n}" for c, n in sorted(codes.items()))
                result.append(f"  {dir_name}/ ({len(files)} files: {desc})")
            else:
                for f in files:
                    result.append(f"  {dir_name}/{f}")

        return "\n".join(result) if result else output

    def _process_diff(self, output: str, command: str = "") -> str:
        lines = output.splitlines()

        # Detect --name-only or --name-status format
        if re.search(r"--name-only\b", command):
            return self._process_name_list(lines)
        if re.search(r"--name-status\b", command):
            return self._process_name_list(lines)

        # Detect stat-only format: `git diff --stat`
        if lines and not any(line.startswith("diff --git") for line in lines):
            return self._process_diff_stat(lines)

        max_hunk = config.get("max_diff_hunk_lines")
        max_context = config.get("max_diff_context_lines")
        result = []
        hunk_line_count = 0
        hunk_truncated = False
        stat_line = ""
        # Leading context: buffer context lines, flush last N when a change appears
        leading_buffer: list[str] = []
        # Trailing context: after a change, emit up to N context lines
        trailing_remaining = 0

        for line in lines:
            if line.startswith("diff --git"):
                leading_buffer = []
                trailing_remaining = 0
                if hunk_truncated:
                    result.append(f"  ... (truncated after {max_hunk} lines)")
                result.append(line)
                hunk_line_count = 0
                hunk_truncated = False
            elif line.startswith(("index ", "---", "+++")):
                continue
            elif line.startswith("@@"):
                leading_buffer = []
                trailing_remaining = 0
                if hunk_truncated:
                    result.append(f"  ... (truncated after {max_hunk} lines)")
                result.append(line)
                hunk_line_count = 0
                hunk_truncated = False
            elif line.startswith(("+", "-")):
                hunk_line_count += 1
                if hunk_line_count <= max_hunk:
                    # Flush leading context (last N lines from buffer)
                    if leading_buffer:
                        result.extend(leading_buffer[-max_context:])
                        leading_buffer = []
                    result.append(line)
                    trailing_remaining = max_context
                elif not hunk_truncated:
                    hunk_truncated = True
            elif line.startswith(" "):
                hunk_line_count += 1
                if hunk_line_count <= max_hunk:
                    if trailing_remaining > 0:
                        # Still emitting trailing context after a change
                        result.append(line)
                        trailing_remaining -= 1
                    else:
                        # Buffer as potential leading context for next change
                        leading_buffer.append(line)
                elif not hunk_truncated:
                    hunk_truncated = True
            elif re.match(r"^\s*\d+ files? changed", line):
                stat_line = line

        if hunk_truncated:
            result.append(f"  ... (truncated after {max_hunk} lines)")
        if stat_line:
            result.append(stat_line)

        return "\n".join(result)

    def _process_name_list(self, lines: list[str]) -> str:
        """Compress --name-only or --name-status output: group by directory."""
        if len(lines) <= 20:
            return "\n".join(lines)

        by_dir: dict[str, list[str]] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # --name-status: "M\tpath/file" or "M  path/file"
            m = re.match(r"^([MADRCTU])\d*\s+(.+)$", stripped)
            if m:
                filepath = m.group(2)
            else:
                filepath = stripped
            parts = filepath.rsplit("/", 1)
            dir_name = parts[0] if len(parts) > 1 else "."
            by_dir.setdefault(dir_name, []).append(stripped)

        total = sum(1 for line in lines if line.strip())
        result = [f"{total} files changed:"]
        for dir_name, files in sorted(by_dir.items()):
            if len(files) > 5:
                result.append(f"  {dir_name}/ ({len(files)} files)")
            else:
                for f in files:
                    result.append(f"  {f}")
        return "\n".join(result)

    def _process_diff_stat(self, lines: list[str]) -> str:
        """Compress `git diff --stat` output: strip visual bars."""
        result = []
        for line in lines:
            # Match stat lines: " path/file | 5 ++-" -> " path/file | 5"
            m = re.match(r"^(\s*.+?\s+\|\s+\d+)\s+[+\-]+\s*$", line)
            if m:
                result.append(m.group(1))
            else:
                result.append(line)
        return "\n".join(result)

    def _process_log(self, output: str, command: str = "") -> str:
        max_entries = config.get("max_log_entries")
        lines = output.splitlines()

        # Detect --graph format (ASCII art: |, *, /, \)
        # Only match lines that contain graph chars (not just spaces)
        has_graph = re.search(r"--graph\b", command) or (
            lines and any(re.match(r"^[|*/\\ ]*[|*/\\]", line) for line in lines[:10])
        )
        if has_graph:
            # Graph format: truncate but preserve structure
            if len(lines) > max_entries * 4:
                kept = lines[: max_entries * 4]
                kept.append(f"... ({len(lines) - max_entries * 4} more lines)")
                return "\n".join(kept)
            return output

        # Detect if already one-line format
        if lines and not lines[0].startswith("commit "):
            # Already compact format -- just truncate
            if len(lines) > max_entries:
                return "\n".join(lines[:max_entries]) + f"\n... ({len(lines) - max_entries} more)"
            return output

        entries = []
        current: list[str] = []
        for line in lines:
            if line.startswith("commit "):
                if current:
                    entries.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            entries.append(current)

        result = []
        for entry in entries[:max_entries]:
            commit_hash = ""
            message = ""
            for line in entry:
                if line.startswith("commit "):
                    commit_hash = line.split()[1][:8]
                elif (
                    line.strip()
                    and not line.startswith(("Author:", "Merge:", "Date:"))
                    and not message
                ):
                    message = line.strip()
            result.append(f"{commit_hash} {message}")

        if len(entries) > max_entries:
            result.append(f"... ({len(entries) - max_entries} more commits)")

        return "\n".join(result)

    def _process_show(self, output: str) -> str:
        # git show is like log + diff -- process the diff portion
        lines = output.splitlines()
        header = []
        diff_start = -1
        for i, line in enumerate(lines):
            if line.startswith("diff --git"):
                diff_start = i
                break
            header.append(line)

        if diff_start == -1:
            return output

        diff_output = "\n".join(lines[diff_start:])
        compressed_diff = self._process_diff(diff_output)

        # Compact the header: keep commit hash + message only
        compact_header = []
        for line in header:
            stripped = line.strip()
            if stripped and not stripped.startswith(("Merge:", "Author:", "Date:")):
                compact_header.append(line)

        return "\n".join(compact_header) + "\n" + compressed_diff

    def _process_transfer(self, output: str) -> str:
        lines = output.splitlines()
        important = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(
                r"^(Receiving|Resolving|Counting|Compressing|"
                r"remote:\s*(Counting|Compressing|Total|Enumerating))",
                stripped,
            ):
                continue
            if re.search(r"\d+%", stripped):
                continue
            important.append(stripped)

        if important:
            return "\n".join(important)
        # All lines were progress -- return last non-empty line
        for line in reversed(lines):
            if line.strip():
                return line.strip()
        return output

    def _process_branch(self, output: str) -> str:
        lines = output.strip().splitlines()
        threshold = config.get("git_branch_threshold")
        if len(lines) <= threshold:
            return output
        current = ""
        branches = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("* "):
                current = stripped
            else:
                branches.append(stripped)
        result = [current] if current else []
        result.append(f"({len(branches)} other branches)")
        # Show first few
        for b in branches[:5]:
            result.append(f"  {b}")
        if len(branches) > 5:
            result.append(f"  ... ({len(branches) - 5} more)")
        return "\n".join(result)

    def _process_stash_list(self, output: str) -> str:
        lines = output.strip().splitlines()
        threshold = config.get("git_stash_threshold")
        if len(lines) <= threshold:
            return output
        return "\n".join(lines[:threshold]) + f"\n... ({len(lines) - threshold} more stashes)"

    def _process_reflog(self, output: str) -> str:
        lines = output.strip().splitlines()
        max_entries = config.get("max_log_entries")
        if len(lines) <= max_entries:
            return output
        return "\n".join(lines[:max_entries]) + f"\n... ({len(lines) - max_entries} more entries)"

    def _process_blame(self, output: str) -> str:
        """Compress git blame: group by author, show line counts."""
        lines = output.strip().splitlines()
        if len(lines) <= 20:
            return output

        by_author: dict[str, int] = {}
        recent_lines: list[str] = []

        for line in lines:
            # Standard blame format: hash (Author YYYY-MM-DD HH:MM:SS +TZ  linenum) content
            m = re.match(r"^[0-9a-f]+\s+\((.+?)\s+\d{4}-\d{2}-\d{2}\s+", line)
            if m:
                author = m.group(1).strip()
                by_author[author] = by_author.get(author, 0) + 1
            # Short blame: ^hash (Author date linenum)
            elif re.match(r"^\^?[0-9a-f]+\s+\(", line):
                m2 = re.match(r"^\^?[0-9a-f]+\s+\((.+?)\s+\d{4}", line)
                if m2:
                    author = m2.group(1).strip()
                    by_author[author] = by_author.get(author, 0) + 1

        if not by_author:
            # Porcelain or unrecognized format -- truncate
            if len(lines) > 50:
                return "\n".join(lines[:40]) + f"\n... ({len(lines) - 40} more lines)"
            return output

        # Show last 10 lines for recent context
        recent_lines = lines[-10:]

        result = [f"{len(lines)} lines, {len(by_author)} authors:"]
        for author, count in sorted(by_author.items(), key=lambda x: -x[1]):
            pct = count * 100 // len(lines)
            result.append(f"  {author}: {count} lines ({pct}%)")

        result.append("")
        result.append("Last 10 lines:")
        result.extend(recent_lines)

        return "\n".join(result)
