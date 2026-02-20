"""Configuration system for Token-Saver.

All thresholds and settings can be overridden via environment variables
or a JSON config file at ~/.token-saver/config.json.
"""

import contextlib
import json
import os

_DEFAULTS = {
    "enabled": True,
    "min_input_length": 200,
    "min_compression_ratio": 0.10,
    "wrap_timeout": 300,
    "max_diff_hunk_lines": 150,
    "max_diff_context_lines": 3,
    "max_log_entries": 20,
    "max_file_lines": 300,
    "file_keep_head": 150,
    "file_keep_tail": 50,
    "generic_truncate_threshold": 500,
    "generic_keep_head": 200,
    "generic_keep_tail": 100,
    "ls_compact_threshold": 20,
    "find_compact_threshold": 30,
    "tree_compact_threshold": 50,
    "lint_example_count": 2,
    "lint_group_threshold": 3,
    "file_code_head_lines": 20,
    "file_code_body_lines": 3,
    "file_log_context_lines": 2,
    "file_csv_head_rows": 5,
    "file_csv_tail_rows": 3,
    "search_max_per_file": 3,
    "search_max_files": 20,
    "kubectl_keep_head": 10,
    "kubectl_keep_tail": 20,
    "docker_log_keep_head": 10,
    "docker_log_keep_tail": 20,
    "git_branch_threshold": 30,
    "git_stash_threshold": 10,
    "max_traceback_lines": 30,
    "db_prune_days": 90,
    "debug": False,
}

ENV_PREFIX = "TOKEN_SAVER_"

_config: dict | None = None


def _load_config() -> dict:
    """Load config from file, then overlay env vars."""
    config = dict(_DEFAULTS)

    # Load from config file if it exists
    from src import data_dir  # noqa: PLC0415

    config_path = os.path.join(data_dir(), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, OSError):
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
            else:
                config[key] = env_val

    return config


def get(key: str):
    """Get a config value."""
    global _config  # noqa: PLW0603
    if _config is None:
        _config = _load_config()
    return _config.get(key, _DEFAULTS.get(key))


def reload():
    """Force reload of configuration."""
    global _config  # noqa: PLW0603
    _config = None
