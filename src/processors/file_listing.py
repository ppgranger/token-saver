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

"""File listing processor: ls, find, tree."""

import collections
import re

from src import config
from src.processors import base
from src.processors import utils


class FileListingProcessor(base.Processor):
    """Reduce directory listings to names, sizes, and grouped paths."""

    priority = 50
    hook_patterns = [
        r"^(ls|find|tree|dir|exa|eza|rsync)\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "file_listing"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(
            re.match(r"\s*(?:\S*/)?(ls|find|tree|dir|exa|eza|rsync)\b", command)
        )

    def process(self, command: str, output: str) -> str:
        """Compress captured output according to this processor's rules.

        Args:
            command: Original shell command used to select output handling.
            output: Captured command output before this transformation.

        Returns:
            Compressed text, or the input when no safe reduction is available.
        """
        if not output or not output.strip():
            return output

        if re.search(r"\bfind\b", command):
            return self._process_find(output)
        if re.search(r"\btree\b", command):
            return self._process_tree(output)
        if re.search(r"\bls\b", command):
            return self._process_ls(output, command)
        if re.search(r"\b(exa|eza)\b", command):
            return self._process_ls(output, command)
        return output

    # Regex for ls -l long-format lines:
    # drwxr-xr-x  5 user group  160 Jan 17 12:34 dirname
    # Regex for ls -l long-format lines (locale-agnostic).
    # We capture: type char, size, and everything after the date as filename.
    # The date field varies by locale (EN: "Jan 12 17:24", FR: "12 janv.
    # 17:24"),
    # so we match it as: groups of (non-digit-word-chars or digits) ending with
    # HH:MM or year.
    _LS_LONG_RE = re.compile(
        r"^([d\-lbcps])"  # 1: type indicator
        r"[rwxsStT\-]{9}[@+.]?\s+"  # permissions
        r"\d+\s+"  # nlinks
        r"\S+\s+"  # owner
        r"\S+\s+"  # group
        r"(\d+)\s+"  # 2: size in bytes
        # Two or three date tokens: month/day and time/year.
        r"(?:\S+\s+){2,3}"
        r"(\S.*?)$"  # 3: filename (rest of line, trimmed)
    )

    def _format_size(self, size: int) -> str:
        """Return a compact byte size using binary unit thresholds."""
        if size < 1024:
            return f"{size}B"
        if size < 1024 * 1024:
            return f"{size / 1024:.0f}K"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}M"
        return f"{size / (1024 * 1024 * 1024):.1f}G"

    def _process_ls(self, output: str, command: str) -> str:
        """Retain listing names and sizes, capping large directories."""
        lines = output.splitlines()

        # If -l flag is used, strip permissions/owner/group/date — keep type,
        # size, name
        if re.search(r"\s-\S*l", command):
            result = []
            for line in lines:
                if line.startswith("total"):
                    continue
                match = self._LS_LONG_RE.match(line)
                if not match:
                    result.append(line)
                    continue
                type_char, size_str, name = match.groups()
                size = int(size_str)
                if type_char == "d":
                    result.append(f"  {name}/")
                elif type_char == "l":
                    result.append(f"  {name}")
                else:
                    result.append(f"  {self._format_size(size):>6}  {name}")

            if not result:
                return output
            # Truncate if very long
            if len(result) > 60:
                kept = result[:50]
                kept.append(f"... ({len(result) - 50} more entries)")
                return "\n".join(kept)
            return "\n".join(result)

        items = [line.strip() for line in lines if line.strip()]
        threshold = config.get("ls_compact_threshold")
        if len(items) <= threshold:
            return output

        # Group by extension
        by_ext: dict[str, list[str]] = collections.defaultdict(list)
        dirs = []
        for item in items:
            if item.endswith(("/", ":")):
                dirs.append(item)
            elif "." in item:
                ext = item.rsplit(".", 1)[1]
                by_ext[ext].append(item)
            else:
                by_ext["(no ext)"].append(item)

        result = [f"{len(items)} items:"]
        if dirs:
            if len(dirs) > 10:
                result.append(
                    f"  dirs ({len(dirs)}): {', '.join(dirs[:8])} ... "
                    f"+{len(dirs) - 8}"
                )
            else:
                result.append(f"  dirs ({len(dirs)}): {', '.join(dirs)}")

        for ext, files in sorted(by_ext.items(), key=lambda x: -len(x[1])):
            if len(files) > 5:
                result.append(
                    f"  *.{ext} ({len(files)}): {', '.join(files[:3])} ..."
                )
            else:
                result.append(f"  *.{ext}: {', '.join(files)}")

        return "\n".join(result)

    def _process_find(self, output: str) -> str:
        """Group paths by directory and summarize large groups."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        threshold = config.get("find_compact_threshold")
        if len(lines) <= threshold:
            return output

        by_dir = utils.group_paths_by_dir(lines)

        # Alphabetical and uncapped, unlike fd: `find` output is a tree the
        # user is reading structurally, so path order carries meaning and
        # dropping directories would hide branches.  The larger extension
        # threshold follows from that — keep listing until it is really long.
        result = [f"{len(lines)} files found:"]
        for dir_path, files in sorted(by_dir.items()):
            result.extend(
                utils.format_dir_group(dir_path, files, ext_threshold=20)
            )

        return "\n".join(result)

    def _process_tree(self, output: str) -> str:
        """Keep the upper tree levels and retain the listing totals."""
        lines = output.splitlines()
        threshold = config.get("tree_compact_threshold")
        if len(lines) <= threshold:
            return output

        # Keep beginning and end (summary)
        keep = threshold - 5
        result = lines[:keep]

        # Find the summary line (usually last line like "X directories, Y
        # files")
        summary = ""
        for line in reversed(lines):
            if re.match(r"\d+\s+director(?:ies|y)\b", line):
                summary = line
                break

        result.append(f"\n... ({len(lines) - keep} lines truncated)")
        if summary:
            result.append(summary)

        return "\n".join(result)
