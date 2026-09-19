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

"""Configuration system for Token-Saver.

All thresholds and settings can be overridden via environment variables or a
JSON config file at ~/.token-saver/config.json.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any

import src


def _debug_log(msg: str) -> None:
    """Print a debug message if TOKEN_SAVER_DEBUG is set.

    Args:
        msg: Diagnostic text written to stderr when debugging is enabled.
    """
    if os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes"):
        print(f"[token-saver] {msg}", file=sys.stderr)


_DEFAULTS = {
    "enabled": True,
    "min_input_length": 1,
    "min_compression_ratio": 0.0,
    "wrap_timeout": 300,
    "max_diff_hunk_lines": 50,
    "max_diff_context_lines": 3,
    "max_log_entries": 10,
    "max_file_lines": 100,
    "file_keep_head": 80,
    "file_keep_tail": 30,
    "generic_truncate_threshold": 200,
    "generic_keep_head": 100,
    "generic_keep_tail": 50,
    # Max error/failure lines rescued from the truncated middle (0 disables).
    "generic_keep_critical": 20,
    # Max error lines the engine re-appends when a processor dropped them
    # (0 disables the safety net entirely).
    "recover_critical_lines": 20,
    "ls_compact_threshold": 15,
    "find_compact_threshold": 20,
    "tree_compact_threshold": 30,
    "lint_example_count": 2,
    "lint_group_threshold": 3,
    "file_code_head_lines": 15,
    "file_code_body_lines": 2,
    "file_log_context_lines": 2,
    "file_csv_head_rows": 3,
    "file_csv_tail_rows": 2,
    "search_max_per_file": 3,
    "search_max_files": 15,
    "kubectl_keep_head": 5,
    "kubectl_keep_tail": 10,
    "docker_log_keep_head": 5,
    "docker_log_keep_tail": 10,
    "git_branch_threshold": 15,
    "git_stash_threshold": 5,
    "max_traceback_lines": 30,
    "db_max_rows": 20,
    "db_prune_days": 90,
    "delta_enabled": False,
    "delta_retention_hours": 24,
    "delta_max_runs": 100,
    "chars_per_token": 4,
    "user_processors_dir": "",
    "cargo_warning_example_count": 2,
    "cargo_warning_group_threshold": 3,
    "jq_passthrough_threshold": 50,
    "disabled_processors": [],
    "redaction_allowlist": [],
    "max_chain_depth": 3,
    "max_output_bytes": 10_000_000,
    "debug": False,
}

ENV_PREFIX = "TOKEN_SAVER_"

_config: dict[str, Any] | None = None


PROJECT_CONFIG_FILE = ".token-saver.json"

#: Keys that a *project*-level ``.token-saver.json`` is not trusted to set.
#:
#: A project config is discovered by walking up from ``cwd`` — meaning any
#: git repo you ``cd`` into can drop one, and it takes effect before you've
#: reviewed a single file in it.  ``user_processors_dir`` is arbitrary code
#: execution: ``discover_processors()`` (invoked at hook import time, on
#: *every* Bash command, whether or not it ends up compressible) imports
#: every ``.py`` file in that directory.  ``disabled_processors`` and
#: ``redaction_allowlist`` don't run code, but they can silently switch off
#: the secret-redaction safety net this same repo could then rely on you not
#: noticing. Delta options control sensitive output retention: a cloned repo
#: must not enable recording or extend retention. These options belong in
#: trusted configuration. None has a legitimate per-project use that
#: ``~/.token-saver/config.json`` or an env var doesn't already cover, so a
#: project file setting them is dropped outright rather than coerced.
_PROJECT_FORBIDDEN_KEYS = frozenset(
    {
        "user_processors_dir",
        "disabled_processors",
        "redaction_allowlist",
        "delta_enabled",
        "delta_retention_hours",
        "delta_max_runs",
    }
)


def _find_project_config() -> str | None:
    """Walk up from cwd to find a .token-saver.json file.

    Stops at filesystem root or user home directory.

    Returns:
        The nearest project configuration path, or None if none is found.
    """
    home = os.path.expanduser("~")
    current = os.getcwd()

    while True:
        candidate = os.path.join(current, PROJECT_CONFIG_FILE)
        if os.path.isfile(candidate):
            return candidate

        parent = os.path.dirname(current)
        # Stop at filesystem root or home directory
        if current in (parent, home):
            break
        current = parent

    return None


def _coerce_value(default_val: Any, raw: Any) -> Any:
    """Coerce a file-config value to the type of its default.

    Returns the coerced value, or ``None`` if it cannot be sensibly coerced
    (caller should then keep the existing/default value).  Unlike env vars, JSON
    values already carry types, but a hand-edited config can still hold a string
    where an int is expected (e.g. ``{"wrap_timeout": "300"}``) or an outright
    wrong type (e.g. ``{"max_chain_depth": "deep"}``) — the latter must not
    reach arithmetic/comparison code downstream.

    Args:
        default_val: Default value whose type defines the accepted
            representation.
        raw: Unvalidated JSON value to convert.

    Returns:
        A compatible value, or None when the value cannot be converted.
    """
    # bool must be checked before int (bool is a subclass of int).
    if isinstance(default_val, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes")
        if isinstance(raw, (int, float)):
            return bool(raw)
        return None
    if isinstance(default_val, int):
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
        if isinstance(raw, str):
            try:
                return int(raw.strip())
            except ValueError:
                return None
        return None
    if isinstance(default_val, float):
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                return float(raw.strip())
            except ValueError:
                return None
        return None
    if isinstance(default_val, list):
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, str):
            return [s.strip() for s in raw.split(",") if s.strip()]
        return None
    # String default
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    return None


def _apply_file_overrides(
    config: dict[str, Any],
    file_config: dict[str, Any],
    source: str,
    *,
    trusted: bool = True,
) -> None:
    """Merge a loaded config file, validating types and dropping unknown keys.

    ``trusted=False`` additionally drops ``_PROJECT_FORBIDDEN_KEYS`` — used for
    project-level ``.token-saver.json``, which (unlike the global config file or
    env vars) can be introduced by simply cloning or ``cd``-ing into a repo you
    don't control.

    Args:
        config: Mutable settings mapping to update in place.
        file_config: Parsed JSON settings; non-mapping values are ignored.
        source: Provenance label saved for accepted settings.
        trusted: Whether this source may set global-only sensitive options.
    """
    if not isinstance(file_config, dict):
        return
    for key, raw in file_config.items():
        if key not in _DEFAULTS:
            # Unknown/typo'd keys are ignored rather than polluting config.
            continue
        if not trusted and key in _PROJECT_FORBIDDEN_KEYS:
            _debug_log(
                f"Ignoring {key!r} from untrusted project config {source} "
                "(set it in ~/.token-saver/config.json or an env var instead)"
            )
            continue
        coerced = _coerce_value(_DEFAULTS[key], raw)
        if coerced is None:
            # Type mismatch that couldn't be coerced — keep prior value.
            continue
        config[key] = coerced
        config.setdefault("_config_source", {})[key] = source


def _load_config() -> dict[str, Any]:
    """Load config: defaults -> global file -> project file -> env vars.

    Returns:
        Resolved settings and per-key provenance after applying precedence.
    """
    config: dict[str, Any] = dict(_DEFAULTS)
    config["_config_source"] = dict.fromkeys(_DEFAULTS, "default")

    # Load from global config file if it exists
    config_path = os.path.join(src.data_dir(), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = json.load(f)
            _apply_file_overrides(config, user_config, f"global:{config_path}")
        except (json.JSONDecodeError, OSError):
            pass

    # Load project-level config (overrides global).  Untrusted: a project's
    # .token-saver.json is discovered just by cd-ing into it — see
    # _PROJECT_FORBIDDEN_KEYS for why some keys never come from here.
    project_config_path = _find_project_config()
    if project_config_path is not None:
        try:
            with open(project_config_path, encoding="utf-8") as f:
                project_config = json.load(f)
            _apply_file_overrides(
                config,
                project_config,
                f"project:{project_config_path}",
                trusted=False,
            )
        except (json.JSONDecodeError, OSError):
            # Invalid project config is silently ignored
            pass

    # Environment variable overrides
    for key, default_val in _DEFAULTS.items():
        env_key = ENV_PREFIX + key.upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            if isinstance(default_val, bool):
                config[key] = env_val.lower() in ("1", "true", "yes")
            elif isinstance(default_val, int):
                with contextlib.suppress(ValueError):
                    config[key] = int(env_val)
            elif isinstance(default_val, float):
                with contextlib.suppress(ValueError):
                    config[key] = float(env_val)
            elif isinstance(default_val, list):
                config[key] = [
                    s.strip() for s in env_val.split(",") if s.strip()
                ]
            else:
                config[key] = env_val
            config.setdefault("_config_source", {})[key] = f"env:{env_key}"

    # Output retention is always bounded, even for trusted configuration. Bad
    # limits fall back to documented defaults instead of disabling expiry.
    for key, maximum in (
        ("delta_retention_hours", 168),
        ("delta_max_runs", 1000),
    ):
        if not 1 <= config[key] <= maximum:
            config[key] = _DEFAULTS[key]
            config["_config_source"][key] = "default"

    return config


def get(key: str) -> Any:
    """Get a config value.

    Args:
        key: Configuration key to look up.

    Returns:
        The effective value, or None for an unknown configuration key.
    """
    global _config  # noqa: PLW0603
    if _config is None:
        _config = _load_config()
    return _config.get(key, _DEFAULTS.get(key))


def reload() -> None:
    """Force reload of configuration."""
    global _config  # noqa: PLW0603
    _config = None
