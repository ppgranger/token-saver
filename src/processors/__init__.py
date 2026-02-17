"""Processor auto-discovery registry.

Scans all .py modules in this package, finds non-abstract Processor
subclasses, instantiates them, and returns them sorted by priority.
"""

import importlib
import inspect
import pkgutil

from .base import Processor


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
