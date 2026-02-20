# Environment Processor

**File:** `src/processors/env.py` | **Priority:** 34 | **Name:** `env`

Handles environment variable listing commands.

## Supported Commands

`env`, `printenv`, `set` (when used standalone, not as prefix like `env FOO=bar cmd`).

## Strategy

- **Filters system variables**: TERM, SHELL, USER, HOME, LANG, LC_*, SSH_*, XDG_*, DISPLAY, DBUS_*, Apple_PubSub, and 40+ other system prefixes
- **Redacts sensitive values**: variables matching KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL, PRIVATE, AUTH, API_KEY, AWS_SECRET, DATABASE_URL, MONGODB_URI, REDIS_URL, STRIPE_, TWILIO_, SENDGRID_, GITHUB_TOKEN, NPM_TOKEN, ENCRYPTION, PASSPHRASE, CERTIFICATE, PEM show `VAR=***`
- **Truncates long values**: PATH-like values (> 200 chars with `:` separators) show first 3 entries + count
- **Summary**: `87 environment variables (23 application-relevant)`
- **Footer**: `(42 system vars hidden, 3 sensitive values redacted)`
- Short outputs (< 10 lines) pass through unchanged
