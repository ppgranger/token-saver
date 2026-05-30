"""Configuration system for Token-Saver.

All thresholds and settings can be overridden via environment variables
or a JSON config file at ~/.token-saver/config.json.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any

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


def _find_project_config() -> str | None:
    """Walk up from cwd to find a .token-saver.json file.

    Stops at filesystem root or user home directory.
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
    (caller should then keep the existing/default value).  Unlike env vars,
    JSON values already carry types, but a hand-edited config can still hold a
    string where an int is expected (e.g. ``{"wrap_timeout": "300"}``) or an
    outright wrong type (e.g. ``{"max_chain_depth": "deep"}``) — the latter
    must not reach arithmetic/comparison code downstream.
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


def _apply_file_overrides(config: dict[str, Any], file_config: dict[str, Any], source: str) -> None:
    """Merge a loaded config file, validating types and dropping unknown keys."""
    if not isinstance(file_config, dict):
        return
    for key, raw in file_config.items():
        if key not in _DEFAULTS:
            # Unknown/typo'd keys are ignored rather than polluting config.
            continue
        coerced = _coerce_value(_DEFAULTS[key], raw)
        if coerced is None:
            # Type mismatch that couldn't be coerced — keep prior value.
            continue
        config[key] = coerced
        config.setdefault("_config_source", {})[key] = source


def _load_config() -> dict[str, Any]:
    """Load config: defaults -> global file -> project file -> env vars."""
    config: dict[str, Any] = dict(_DEFAULTS)
    config["_config_source"] = dict.fromkeys(_DEFAULTS, "default")

    # Load from global config file if it exists
    from src import data_dir  # noqa: PLC0415

    config_path = os.path.join(data_dir(), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                user_config = json.load(f)
            _apply_file_overrides(config, user_config, f"global:{config_path}")
        except (json.JSONDecodeError, OSError):
            pass

    # Load project-level config (overrides global)
    project_config_path = _find_project_config()
    if project_config_path is not None:
        try:
            with open(project_config_path) as f:
                project_config = json.load(f)
            _apply_file_overrides(config, project_config, f"project:{project_config_path}")
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
                config[key] = [s.strip() for s in env_val.split(",") if s.strip()]
            else:
                config[key] = env_val
            config.setdefault("_config_source", {})[key] = f"env:{env_key}"

    return config


def get(key: str) -> Any:
    """Get a config value."""
    global _config  # noqa: PLW0603
    if _config is None:
        _config = _load_config()
    return _config.get(key, _DEFAULTS.get(key))


def reload() -> None:
    """Force reload of configuration."""
    global _config  # noqa: PLW0603
    _config = None
