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

"""Summarize pip, Poetry, and uv installation output."""

import re

from src.processors import base

_PIP_INSTALL_RE = re.compile(
    rf"\bpip3?\s+install\b|{base.PYTHON_CMD}\s+-m\s+pip\s+install\b"
)
_POETRY_RE = re.compile(r"\bpoetry\s+(install|update|add)\b")
_UV_RE = re.compile(r"\buv\s+(pip\s+install|sync)\b")

_COLLECTING_RE = re.compile(r"^\s*Collecting\s+")
_DOWNLOADING_RE = re.compile(r"^\s*(Downloading|Using cached)\s+")
_PROGRESS_RE = re.compile(r"^\s*━|^\s*\[.*\]\s+\d+%|^\s*\d+\.\d+\s*(kB|MB|GB)")
_ALREADY_RE = re.compile(r"^\s*Requirement already satisfied")
_INSTALLING_RE = re.compile(r"^\s*Installing collected packages:")
_SUCCESS_RE = re.compile(r"^\s*Successfully installed\s+(.+)")
_RESOLVING_RE = re.compile(
    r"^\s*(Resolving dependencies|Updating dependencies)"
)
_POETRY_INSTALL_RE = re.compile(
    r"^\s*(Installing|Updating|Removing)\s+(\S+)\s+\((.+?)\)"
)
_UV_RESOLVED_RE = re.compile(r"^\s*Resolved\s+(\d+)\s+packages?")
_UV_INSTALLED_RE = re.compile(
    r"^\s*(Installed|Uninstalled)\s+(\d+)\s+packages?"
)
_ERROR_RE = re.compile(
    r"\b(error|Error|ERROR|exception|Exception|"
    r"Could not|cannot|Cannot|FAILED|failed|"
    r"conflict|Conflict|incompatible)\b"
)
_WARNING_RE = re.compile(r"\b(warning|Warning|WARNING|DEPRECATION)\b")


class PythonInstallProcessor(base.Processor):
    """Summarize pip, Poetry, and uv dependency installation output."""

    priority = 24
    handles_failure = True
    hook_patterns = [
        (
            r"^(pip3?\s+install|poetry\s+(install|update|add)|"
            r"uv\s+(pip\s+install|sync))\b"
        ),
        rf"^{base.PYTHON_CMD}\s+-m\s+pip\s+install\b",
    ]

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "python_install"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        if re.search(r"\bpip3?\s+(list|freeze)\b", command):
            return False
        return bool(
            _PIP_INSTALL_RE.search(command)
            or _POETRY_RE.search(command)
            or _UV_RE.search(command)
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

        if _POETRY_RE.search(command):
            return self._process_poetry(output)
        if _UV_RE.search(command):
            return self._process_uv(output)
        return self._process_pip(output)

    def _process_pip(self, output: str) -> str:
        """Group installed packages and retain pip diagnostics and status."""
        lines = output.splitlines()
        result: list[str] = []
        collecting_count = 0
        downloading_count = 0
        already_count = 0
        installed_packages: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if _COLLECTING_RE.match(stripped):
                collecting_count += 1
            elif _DOWNLOADING_RE.match(stripped) or _PROGRESS_RE.match(
                stripped
            ):
                downloading_count += 1
            elif _ALREADY_RE.match(stripped):
                already_count += 1
            elif _INSTALLING_RE.match(stripped):
                continue
            elif m := _SUCCESS_RE.match(stripped):
                pkgs = m.group(1).split()
                installed_packages.extend(pkgs)
            elif _ERROR_RE.search(stripped):
                errors.append(line)
            elif _WARNING_RE.search(stripped):
                warnings.append(line)

        if collecting_count:
            result.append(f"[{collecting_count} packages collected]")
        if downloading_count:
            result.append(f"[{downloading_count} downloads]")
        if already_count:
            result.append(f"[{already_count} already satisfied]")

        if errors:
            result.extend(errors)

        if warnings:
            result.extend(warnings[:5])
            if len(warnings) > 5:
                result.append(f"... ({len(warnings) - 5} more warnings)")

        if installed_packages:
            result.append(
                f"Successfully installed {len(installed_packages)} packages:"
            )
            # Show first 10 packages, summarize rest
            for pkg in installed_packages[:10]:
                result.append(f"  {pkg}")
            if len(installed_packages) > 10:
                result.append(f"  ... ({len(installed_packages) - 10} more)")

        return "\n".join(result) if result else output

    def _process_poetry(self, output: str) -> str:
        """Count Poetry operations and retain warnings and failure details."""
        lines = output.splitlines()
        result: list[str] = []
        installed: list[str] = []
        updated: list[str] = []
        removed: list[str] = []
        errors: list[str] = []
        resolving_skipped = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if _RESOLVING_RE.match(stripped):
                resolving_skipped += 1
                continue

            m = _POETRY_INSTALL_RE.match(stripped)
            if m:
                action, pkg, version = m.groups()
                if action == "Installing":
                    installed.append(f"{pkg} ({version})")
                elif action == "Updating":
                    updated.append(f"{pkg} ({version})")
                elif action == "Removing":
                    removed.append(pkg)
                continue

            if _ERROR_RE.search(stripped):
                errors.append(line)

        if resolving_skipped:
            result.append(f"[dependency resolution: {resolving_skipped} steps]")

        if errors:
            result.extend(errors)

        if installed:
            result.append(f"Installed {len(installed)} packages:")
            for pkg in installed[:10]:
                result.append(f"  {pkg}")
            if len(installed) > 10:
                result.append(f"  ... ({len(installed) - 10} more)")

        if updated:
            result.append(f"Updated {len(updated)} packages:")
            for pkg in updated[:5]:
                result.append(f"  {pkg}")
            if len(updated) > 5:
                result.append(f"  ... ({len(updated) - 5} more)")

        if removed:
            result.append(f"Removed {len(removed)} packages")

        return "\n".join(result) if result else output

    def _process_uv(self, output: str) -> str:
        """Summarize uv changes while retaining dependency diagnostics."""
        lines = output.splitlines()
        result: list[str] = []
        errors: list[str] = []
        resolved = 0
        installed = 0
        uninstalled = 0
        downloading_count = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            m = _UV_RESOLVED_RE.match(stripped)
            if m:
                resolved = int(m.group(1))
                continue

            m = _UV_INSTALLED_RE.match(stripped)
            if m:
                action = m.group(1)
                count = int(m.group(2))
                if action == "Installed":
                    installed = count
                else:
                    uninstalled = count
                continue

            if _DOWNLOADING_RE.match(stripped) or _PROGRESS_RE.match(stripped):
                downloading_count += 1
                continue

            if _ERROR_RE.search(stripped):
                errors.append(line)

        if resolved:
            result.append(f"Resolved {resolved} packages")
        if downloading_count:
            result.append(f"[{downloading_count} downloads]")
        if errors:
            result.extend(errors)
        if installed:
            result.append(f"Installed {installed} packages")
        if uninstalled:
            result.append(f"Uninstalled {uninstalled} packages")

        return "\n".join(result) if result else output
