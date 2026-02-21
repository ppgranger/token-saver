"""Environment variable processor: env, printenv, set."""

import re

from .base import Processor

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

# Patterns for sensitive variable names
_SENSITIVE_PATTERNS = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE|AUTH|API_KEY|"
    r"ACCESS_KEY|AWS_SECRET|DATABASE_URL|MONGODB_URI|REDIS_URL|"
    r"STRIPE_|TWILIO_|SENDGRID_|GITHUB_TOKEN|NPM_TOKEN|"
    r"ENCRYPTION|PASSPHRASE|CERTIFICATE|PEM)",
    re.IGNORECASE,
)


class EnvProcessor(Processor):
    priority = 34
    hook_patterns = [
        r"^(env|printenv|set)\s*$",
    ]

    @property
    def name(self) -> str:
        return "env"

    def can_handle(self, command: str) -> bool:
        return bool(re.match(r"^\s*(env|printenv|set)\s*$", command))

    def process(self, command: str, output: str) -> str:
        if not output or not output.strip():
            return output

        lines = output.splitlines()
        if len(lines) <= 10:
            return output

        system_count = 0
        app_vars = []
        sensitive_redacted = 0

        for line in lines:
            stripped = line.strip()
            if not stripped or "=" not in stripped:
                continue

            key = stripped.split("=", 1)[0]
            value = stripped.split("=", 1)[1]

            # Filter system variables
            if any(key.startswith(prefix) for prefix in _SYSTEM_PREFIXES):
                system_count += 1
                continue

            # Redact sensitive values
            if _SENSITIVE_PATTERNS.search(key):
                app_vars.append(f"  {key}=***")
                sensitive_redacted += 1
                continue

            # Truncate very long values (PATH-like)
            if len(value) > 200:
                parts = value.split(":")
                if len(parts) > 3:
                    value = ":".join(parts[:3]) + f":... ({len(parts)} total entries)"
                else:
                    value = value[:150] + f"... ({len(value)} chars)"
                app_vars.append(f"  {key}={value}")
            else:
                app_vars.append(f"  {stripped}")

        total = len(lines)
        result = [f"{total} environment variables ({len(app_vars)} application-relevant):"]
        result.extend(app_vars)

        notes = []
        if system_count:
            notes.append(f"{system_count} system vars hidden")
        if sensitive_redacted:
            notes.append(f"{sensitive_redacted} sensitive values redacted")
        if notes:
            result.append(f"({', '.join(notes)})")

        return "\n".join(result)
