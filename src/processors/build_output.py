"""Build output processor: npm, cargo, make, webpack, tsc, pip, docker, npm audit."""

import re

from .base import Processor


class BuildOutputProcessor(Processor):
    priority = 25
    hook_patterns = [
        r"^(npm\s+(run|install|build|ci|audit)|yarn\s+(run|install|build|add|audit)|pnpm\s+(run|install|build|add|audit))\b",
        r"^(cargo\s+(build|check|clippy)|make\b|cmake\b|gradle\b|mvn\b|ant\b)",
        r"^(pip3?\s+install|poetry\s+(install|update)|uv\s+(pip|sync))\b",
        r"^(tsc|webpack|vite(\s+build)?|esbuild|rollup|next\s+build|nuxt\s+build)\b",
    ]

    @property
    def name(self) -> str:
        return "build"

    def can_handle(self, command: str) -> bool:
        # Exclude package listing commands (handled by PackageListProcessor)
        if re.search(r"\b(pip3?\s+(list|freeze)|npm\s+(ls|list)|conda\s+list)\b", command):
            return False
        return bool(
            re.search(
                r"\b(npm\s+(run|install|ci|build|audit)|yarn\s+(install|build|add|audit)|pnpm\s+(install|build|add|audit)|"
                r"cargo\s+(build|check)|make\b|cmake\b|gradle\b|mvn\b|ant\b|"
                r"pip3?\s+install|poetry\s+(install|update)|uv\s+(pip|sync)|"
                r"tsc\b|webpack\b|vite(\s+build)?|esbuild\b|rollup\b|next\s+build|nuxt\s+build|"
                r"docker\s+(build|compose\s+build))\b",
                command,
            )
        )

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        if re.search(r"\b(npm|yarn|pnpm)\s+audit\b", command):
            return self._process_audit(output)
        if re.search(r"\bdocker\s+(build|compose\s+build)\b", command):
            return self._process_docker_build(output)

        lines = output.splitlines()

        has_error = any(
            re.search(r"\b(error|Error|ERROR)\b", line)
            and not re.search(r"\b0 errors?\b", line)
            and not self._is_progress_line(line.strip())
            for line in lines
        )

        if has_error:
            return self._extract_errors(lines)
        return self._summarize_success(lines)

    def _extract_errors(self, lines: list[str]) -> str:
        result = []
        in_error_block = False
        blank_count = 0

        for line in lines:
            stripped = line.strip()

            if self._is_progress_line(stripped):
                continue

            # Error start
            if re.search(r"\b(error|Error|ERROR)\b", stripped) and not re.search(
                r"\b0 errors?\b", stripped
            ):
                in_error_block = True
                blank_count = 0
                result.append(line)
                continue

            if in_error_block:
                if not stripped:
                    blank_count += 1
                    if blank_count >= 2:
                        in_error_block = False
                    else:
                        result.append(line)
                    continue
                blank_count = 0
                # Context lines (stack trace, code pointers, etc.)
                if (
                    stripped.startswith(("at ", "-->", "  |", "   |", ">", "~~", "^^"))
                    or re.match(r"^\d+\s*\|", stripped)
                    or re.match(r"^\s+\d+:\d+", stripped)
                ):
                    result.append(line)
                elif re.search(r"\b(warning|Warning|note|Note|help|Help)\b", stripped):
                    result.append(line)
                    in_error_block = False
                else:
                    result.append(line)
                continue

            # Keep summary lines
            if re.search(r"\d+\s+(errors?|warnings?|problems?)", stripped.lower()):
                result.append(line)

        if not result:
            return "\n".join(lines[-30:])
        return "\n".join(result)

    def _summarize_success(self, lines: list[str]) -> str:
        result = []
        warning_count = 0
        output_lines = []

        for line in lines:
            stripped = line.strip()

            if self._is_progress_line(stripped):
                continue

            if re.search(r"\bwarn(ing)?\b", stripped, re.IGNORECASE):
                warning_count += 1
                continue

            # Keep meaningful output lines
            if any(
                kw in stripped.lower()
                for kw in [
                    "built",
                    "compiled",
                    "success",
                    "done",
                    "complete",
                    "finish",
                    "written",
                    "created",
                    "generated",
                    "output",
                    "bundle",
                    "size",
                    "gzip",
                    "chunk",
                ]
            ):
                output_lines.append(stripped)

        summary = "Build succeeded."
        if warning_count > 0:
            summary += f" ({warning_count} warnings)"

        result.append(summary)
        # Keep last few meaningful lines (often contain size/timing info)
        if output_lines:
            result.extend(output_lines[-3:])

        return "\n".join(result)

    def _process_docker_build(self, output: str) -> str:
        """Compress docker build output: keep steps, errors, final result."""
        lines = output.splitlines()
        result = []
        step_count = 0

        for line in lines:
            stripped = line.strip()

            # Keep step headers
            if re.match(r"^(Step \d+/\d+|#\d+\s|\[\d+/\d+\])", stripped):
                step_count += 1
                result.append(stripped)
                continue

            # Always keep errors
            if re.search(r"\b(error|Error|ERROR|failed|FAILED)\b", stripped):
                result.append(stripped)
                continue

            # Keep final image/tag info
            if re.search(
                r"(Successfully (built|tagged)|naming to |writing image|DONE)",
                stripped,
                re.IGNORECASE,
            ):
                result.append(stripped)
                continue

            # Skip noise: intermediate containers, sha256 hashes, RUN output details
            if re.match(r"^(Running in |Removing intermediate| ---> |sha256:)", stripped):
                continue
            if re.match(r"^(Sending build context|Downloading|Extracting|Pulling)", stripped):
                continue
            if re.search(r"\d+(\.\d+)?%", stripped):
                continue

        if not result:
            return "\n".join(lines[-10:])
        return "\n".join(result)

    def _process_audit(self, output: str) -> str:
        """Compress npm/yarn audit: group vulnerabilities by severity."""
        lines = output.splitlines()
        severities: dict[str, int] = {}
        packages: dict[str, list[str]] = {}  # severity -> package names
        summary_lines = []
        current_package = ""

        for line in lines:
            stripped = line.strip()

            # Severity detection
            sev_match = re.search(r"\b(critical|high|moderate|low)\b", stripped, re.IGNORECASE)

            # Package name in vulnerability blocks
            pkg_match = re.match(r"^(\S+)\s+[<>=]", stripped)
            if not pkg_match:
                pkg_match = re.match(r"^Package\s+(\S+)", stripped)

            if pkg_match:
                current_package = pkg_match.group(1)

            if sev_match:
                sev = sev_match.group(1).lower()
                severities[sev] = severities.get(sev, 0) + 1
                if current_package:
                    packages.setdefault(sev, [])
                    if current_package not in packages[sev]:
                        packages[sev].append(current_package)

            # Keep summary/total lines
            if re.search(r"\d+\s+(vulnerabilit|package)", stripped, re.IGNORECASE):
                summary_lines.append(stripped)

            # Keep fix recommendation lines
            if re.search(r"(npm audit fix|run .* to fix|breaking change)", stripped, re.IGNORECASE):
                summary_lines.append(stripped)

        if not severities:
            # Could not parse — fall through to generic
            return "\n".join(lines)

        result = []
        total = sum(severities.values())
        result.append(f"{total} vulnerabilities found:")
        for sev in ["critical", "high", "moderate", "low"]:
            if sev in severities:
                pkgs = packages.get(sev, [])
                pkg_str = f" ({', '.join(pkgs[:5])})" if pkgs else ""
                if len(pkgs) > 5:
                    pkg_str = f" ({', '.join(pkgs[:5])} +{len(pkgs) - 5} more)"
                result.append(f"  {sev}: {severities[sev]}{pkg_str}")

        # Deduplicate summary lines
        seen = set()
        for line in summary_lines:
            if line not in seen:
                result.append(line)
                seen.add(line)

        return "\n".join(result)

    def _is_progress_line(self, line: str) -> bool:
        if not line:
            return False
        patterns = [
            r"^\s*(Downloading|Installing|Fetching|Resolving|Unpacking|Linking|Extracting)",
            r"^\s*added \d+ packages?",
            r"^\s*\d+ packages? are looking",
            r"^\s*(GET|fetch)\s+http",
            r"^\s*npm\s+(WARN|notice|warn)\b",
            r"^\s*\d+(\.\d+)?\s*%",
            r"^\s*(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏|⣾|⣽|⣻|⢿|⡿|⣟|⣯|⣷)",
            r"^\s*\[\d+/\d+\]",  # [1/5] progress indicators
            r"^\s*(Compiling|Compiling|Updating|Preparing)\s+\S+",  # cargo
            r"^\s*Already up to date",
            r"^\s*Using\s+(cached|version)\b",
            r"^\s*Collecting\s+\S+",  # pip
            r"^\s*━",  # pip progress bar
            r"^.*(Resolution|Fetch|Link)\s+step\b",  # yarn berry v2+ (prefixed with ➤ YN0000: ┌)
            r"^\s*Progress:\s+resolved\s+\d+",  # pnpm resolved/reused/downloaded stats
            r"^\s*[Pp]ackages?\s+(are|is)\s+hard linked",  # pnpm content-addressable store
        ]
        return any(re.match(p, line) for p in patterns)
