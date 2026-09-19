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

"""Environment variable processor: env, printenv, set."""

import re

from src import config
from src.processors import base
from src.processors import critical

# System variables that are rarely useful for debugging
_SYSTEM_PREFIXES = (
    "TERM",
    "SHELL",
    "USER",
    "LOGNAME",
    "HOME",
    "LANG",
    "LC_",
    "SSH_",
    "DISPLAY",
    "XDG_",
    "DBUS_",
    "WINDOWID",
    "COLORTERM",
    "SHLVL",
    "OLDPWD",
    "_",
    "LESS",
    "PAGER",
    "EDITOR",
    "VISUAL",
    "MAIL",
    "MANPATH",
    "INFOPATH",
    "GPG_",
    "GNOME_",
    "GTK_",
    "QT_",
    "DESKTOP_",
    "SESSION_",
    "KONSOLE_",
    "TERM_PROGRAM",
    "TMPDIR",
    "ZDOTDIR",
    "ZSH",
    "BASH",
    "LS_COLORS",
    "LSCOLORS",
    "HISTSIZE",
    "HISTFILE",
    "HISTCONTROL",
    "SAVEHIST",
    "COMP_WORDBREAKS",
    "Apple_PubSub",
    "LaunchInstanceID",
    "__CF",
    "__CFBundle",
    "SECURITYSESSION",
    "COMMAND_MODE",
)

# Patterns for sensitive variable names.
#
# Two tiers:
#   * Unambiguous substrings — long/specific enough to match anywhere without
#     colliding with ordinary words.
#   * Ambiguous tokens (KEY, AUTH, PASS, PWD, PAT, DSN, …) — matched only at
#     letter boundaries so MONKEY / AUTHOR / KEYBOARD / PATH are NOT redacted.
#     Note: \b is unusable here because "_" is a regex word char, so "API_KEY"
#     would not satisfy \bKEY\b.  We use letter-only lookarounds instead, which
#     treat "_", digits and string edges as separators.
_UNAMBIGUOUS_SECRET = (
    r"SECRET|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL|PRIVATE|"  # noqa: S105
    r"ENCRYPT|CERTIFICATE|APIKEY|API_KEY|ACCESS_KEY|AWS_SECRET|"
    r"DATABASE_URL|DATABASE_PASSWORD|MONGODB_URI|REDIS_URL|CONNECTION_STRING|"
    r"STRIPE_|TWILIO_|SENDGRID_|GITHUB_TOKEN|NPM_TOKEN|WEBHOOK|BEARER"
)
_AMBIGUOUS_SECRET = (
    r"(?<![A-Za-z])(?:KEY|KEYS|TOKEN|AUTH|PAT|DSN|PASS|PWD|PEM|"  # noqa: S105
    r"CERT)(?![A-Za-z])"
)
_SENSITIVE_PATTERNS = re.compile(
    rf"({_UNAMBIGUOUS_SECRET}|{_AMBIGUOUS_SECRET})",
    re.IGNORECASE,
)


def _redaction_allowlist() -> set[str]:
    """Return uppercase names explicitly permitted to appear unredacted."""
    return {
        str(name).upper() for name in config.get("redaction_allowlist") or []
    }


def is_sensitive_name(name: str) -> bool:
    """Return whether an environment variable name indicates a secret.

    Args:
        name: Variable name without its value or assignment operator.

    Returns:
        Whether the shared secret-name pattern matches, before allowlisting.
    """
    return bool(_SENSITIVE_PATTERNS.search(name))


class EnvProcessor(base.Processor):
    """Redact sensitive environment values and group remaining variables."""

    priority = 34
    hook_patterns = [
        r"^(env|printenv|set)\s*$",
    ]

    def redacted_secrets(self, command: str, output: str) -> bool:
        # Cheap, conservative pre-check mirroring process()'s own redaction
        # logic (system-var filtering aside — a false positive
        # here only costs the ratio-fallback safety net on an output that
        # turns out to have nothing sensitive, never the reverse).
        """Return whether processing this input would mask sensitive values.

        Args:
            command: Shell command identifying the input format.
            output: Captured output that may contain sensitive values.

        Returns:
            Whether unredacted input must be excluded from fallback results.
        """
        allowlist = _redaction_allowlist()
        for line in output.splitlines():
            if "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key.upper() not in allowlist and _SENSITIVE_PATTERNS.search(key):
                return True
        return False

    @property
    def name(self) -> str:
        """The stable name used for processor routing and savings tracking."""
        return "env"

    def can_handle(self, command: str) -> bool:
        """Return whether this processor supports the supplied command.

        Args:
            command: Shell command text used for routing.

        Returns:
            Whether the command matches this processor's supported tools.
        """
        return bool(re.match(r"^\s*(env|printenv|set)\s*$", command))

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

        lines = output.splitlines()
        # Names the user has marked safe to show verbatim (case-insensitive),
        # e.g. GIT_AUTHOR_NAME or PUBLIC_KEY that would otherwise be redacted.
        allowlist = _redaction_allowlist()

        if len(lines) <= 10:
            # Short output needs no summarization, but still needs redaction.
            # Preserve every other line and its ending, including system vars
            # and diagnostics that the long-output summary would omit.
            safe_lines = []
            for line in output.splitlines(keepends=True):
                key, separator, _ = line.partition("=")
                if (
                    separator
                    and key.strip().upper() not in allowlist
                    and _SENSITIVE_PATTERNS.search(key)
                ):
                    ending = line[len(line.rstrip("\r\n")) :]
                    safe_lines.append(f"{key}=***{ending}")
                else:
                    safe_lines.append(line)
            return "".join(safe_lines)

        system_count = 0
        app_vars = []
        diagnostics = []
        sensitive_redacted = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if "=" not in stripped:
                # Retain diagnostics here: once secrets have been redacted,
                # the engine cannot safely recover lines from the raw input.
                if critical.is_critical(stripped):
                    diagnostics.append(stripped)
                continue

            key = stripped.split("=", 1)[0].strip()
            value = stripped.split("=", 1)[1]

            # Filter system variables
            if any(key.startswith(prefix) for prefix in _SYSTEM_PREFIXES):
                system_count += 1
                continue

            # Redact sensitive values, unless explicitly allowlisted
            if key.upper() not in allowlist and _SENSITIVE_PATTERNS.search(key):
                app_vars.append(f"  {key}=***")
                sensitive_redacted += 1
                continue

            # Truncate very long values (PATH-like)
            if len(value) > 200:
                parts = value.split(":")
                if len(parts) > 3:
                    value = (
                        ":".join(parts[:3])
                        + f":... ({len(parts)} total entries)"
                    )
                else:
                    value = value[:150] + f"... ({len(value)} chars)"
                app_vars.append(f"  {key}={value}")
            else:
                app_vars.append(f"  {stripped}")

        total = len(lines)
        result = [
            (
                f"{total} environment variables ({len(app_vars)} "
                f"application-relevant):"
            )
        ]
        result.extend(app_vars)
        result.extend(diagnostics)

        notes = []
        if system_count:
            notes.append(f"{system_count} system vars hidden")
        if sensitive_redacted:
            notes.append(f"{sensitive_redacted} sensitive values redacted")
        if notes:
            result.append(f"({', '.join(notes)})")

        return "\n".join(result)
