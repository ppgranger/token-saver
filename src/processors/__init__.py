"""Processor auto-discovery registry.

Scans all .py modules in this package, finds non-abstract Processor
subclasses, instantiates them, and returns them sorted by priority.

Also loads user-defined processors from ~/.token-saver/processors/ (or
a custom directory set via the ``user_processors_dir`` config key).
"""

import importlib
import importlib.util
import inspect
import os
import pkgutil
import sys

from .base import Processor


def _load_user_processors(user_dir: str) -> None:
    """Import .py files from a user processors directory.

    Each file is expected to define one or more Processor subclasses.
    Errors are logged and skipped so a broken user processor never
    crashes the engine.
    """
    if not os.path.isdir(user_dir):
        return

    for filename in sorted(os.listdir(user_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        filepath = os.path.join(user_dir, filename)
        module_name = f"_user_processor_{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        except Exception as exc:
            _debug_log(f"Skipping user processor {filename}: {exc}")


def _debug_log(msg: str) -> None:
    """Print a debug message if TOKEN_SAVER_DEBUG is set."""
    if os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes"):
        print(f"[token-saver] {msg}", file=sys.stderr)


def _get_user_processors_dir() -> str:
    """Return the user processors directory from config or default."""
    from .. import config  # noqa: PLC0415

    custom_dir = config.get("user_processors_dir")
    if custom_dir:
        return os.path.expanduser(str(custom_dir))

    from .. import data_dir  # noqa: PLC0415

    return os.path.join(data_dir(), "processors")


def discover_processors() -> list[Processor]:
    """Auto-discover all Processor subclasses in this package.

    Returns instantiated processors sorted by priority (lowest first).
    GenericProcessor (priority 999) is always last.
    """
    package_path = __path__
    package_name = __name__

    # Import all modules in this package (skip __init__ and base)
    for _finder, module_name, _is_pkg in pkgutil.iter_modules(package_path):
        if module_name in ("base",):
            continue
        importlib.import_module(f".{module_name}", package_name)

    # Load user-defined processors
    user_dir = _get_user_processors_dir()
    _load_user_processors(user_dir)

    # Find all non-abstract Processor subclasses
    def _all_subclasses(cls):
        result = set()
        for sub in cls.__subclasses__():
            if not inspect.isabstract(sub):
                result.add(sub)
            result.update(_all_subclasses(sub))
        return result

    subclasses = _all_subclasses(Processor)
    instances = [cls() for cls in subclasses]
    instances.sort(key=lambda p: p.priority)

    # Validate: GenericProcessor must be last
    if instances and instances[-1].priority != 999:
        raise RuntimeError(
            f"GenericProcessor (priority 999) must be the lowest-priority processor, "
            f"but last processor is {instances[-1].name!r} with priority {instances[-1].priority}"
        )

    return instances


def collect_hook_patterns() -> list[str]:
    """Collect all hook_patterns from discovered processors.

    Returns a flat list of regex pattern strings, used by hook_pretool.py.
    """
    patterns: list[str] = []
    for processor in discover_processors():
        patterns.extend(processor.hook_patterns)
    return patterns
