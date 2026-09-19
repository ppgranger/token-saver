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

import src
from src import config
from src import registry as processor_registry
from src.processors import base

#: Module-name prefix given to processors loaded from the user directory.
_USER_MODULE_PREFIX = "_user_processor_"


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
        module_name = f"{_USER_MODULE_PREFIX}{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        # User modules may raise any exception during import. Isolate each
        # plugin so one broken extension cannot prevent command output.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _debug_log(f"Skipping user processor {filename}: {exc}")


def _debug_log(msg: str) -> None:
    """Print a debug message if TOKEN_SAVER_DEBUG is set."""
    if os.environ.get("TOKEN_SAVER_DEBUG", "").lower() in ("1", "true", "yes"):
        print(f"[token-saver] {msg}", file=sys.stderr)


def _get_user_processors_dir() -> str:
    """Return the user processors directory from config or default."""
    custom_dir = config.get("user_processors_dir")
    if custom_dir:
        return os.path.expanduser(str(custom_dir))

    return os.path.join(src.data_dir(), "processors")


def _is_registrable(cls: type) -> bool:
    """Return True if ``cls`` is a processor this registry should own.

    ``Processor.__subclasses__()`` sees *every* subclass defined anywhere in
    the process, not just the ones we loaded.  Without this filter, a subclass
    declared in a test module — or in any third-party code that happens to
    import ``Processor`` — silently joins the routing table for the rest of
    the process.  Only this package and the user processors directory count.
    """
    module = getattr(cls, "__module__", "") or ""
    return module.startswith((f"{__name__}.", _USER_MODULE_PREFIX))


def discover_processors() -> list[base.Processor]:
    """Auto-discover all Processor subclasses in this package.

    Returns:
        Instantiated processors in ascending priority order. The generic
        fallback, with priority 999, is last.

    Raises:
        RuntimeError: The discovered processors violate registry invariants.
    """
    package_path = __path__
    package_name = __name__

    # Import all modules in this package (skip __init__ and base)
    for _, module_name, _ in pkgutil.iter_modules(package_path):
        if module_name in ("base",):
            continue
        importlib.import_module(f".{module_name}", package_name)

    # Load user-defined processors
    user_dir = _get_user_processors_dir()
    _load_user_processors(user_dir)

    # Find all non-abstract Processor subclasses
    def _all_subclasses(cls):
        """Collect concrete subclasses belonging to loaded processor modules."""
        result = set()
        for sub in cls.__subclasses__():
            if not inspect.isabstract(sub) and _is_registrable(sub):
                result.add(sub)
            result.update(_all_subclasses(sub))
        return result

    subclasses = _all_subclasses(base.Processor)
    instances = [cls() for cls in subclasses]
    # Keep discovery's existing RuntimeError contract for invalid plugins.
    try:
        return processor_registry.ProcessorRegistry(instances).processors
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def collect_hook_patterns() -> list[str]:
    """Collect all hook_patterns from discovered processors.

    Disabled processors are excluded so their commands are not intercepted.

    Returns:
        A flat list of regex pattern strings consumed by platform hooks.
    """
    raw_disabled = config.get("disabled_processors") or []
    registry = processor_registry.ProcessorRegistry(
        discover_processors(),
        disabled=raw_disabled if isinstance(raw_disabled, list) else [],
    )
    return registry.hook_patterns()
