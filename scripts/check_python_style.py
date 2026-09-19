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

"""Check structural Google Python style rules without importing checked code.

This supplements Ruff and Pylint with module-only imports and simple
comprehensions. It validates static module paths, not dynamic re-exports or
complete compliance with the prose style guide.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
import sysconfig
from importlib import machinery

_TYPING_MODULES = frozenset(
    {"__future__", "typing", "typing_extensions", "collections.abc"}
)
_DEFAULT_PATHS = (
    "src",
    "scripts",
    "installers",
    "antigravity",
    "examples",
    "tests",
    "install.py",
    "bin/token-saver",
)


def _is_module(name: str, import_roots: tuple[pathlib.Path, ...]) -> bool:
    """Check module files and package directories without loading any code."""
    if name in sys.builtin_module_names:
        return True
    parts = name.split(".")
    suffixes = (".py", *machinery.EXTENSION_SUFFIXES)
    for root in import_roots:
        candidate = root.joinpath(*parts)
        # A directory can be a regular package or an implicit namespace package.
        if candidate.is_dir():
            return True
        if any(
            candidate.with_name(candidate.name + suffix).is_file()
            for suffix in suffixes
        ):
            return True
    return False


def check_source(
    source: str,
    path: pathlib.Path,
    *,
    import_roots: tuple[pathlib.Path, ...],
) -> list[str]:
    """Inspect Python syntax for module imports and simple comprehensions.

    Args:
        source: Python source to parse; no source code is executed.
        path: Filename included in diagnostics.
        import_roots: Directories containing available top-level modules. Module
            resolution checks only filesystem paths and built-in module names.

    Returns:
        Diagnostics with filename, line number, rule identifier, and message.
        Syntax errors are reported as diagnostics rather than raised.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [f"{path}:{error.lineno or 1}: syntax: {error.msg}"]
    errors = []
    for node in ast.walk(tree):
        prefix = f"{path}:{getattr(node, 'lineno', 1)}"
        if isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append(
                    f"{prefix}: absolute-import: use an absolute module path"
                )
                continue
            for alias in node.names:
                if alias.name == "*":
                    errors.append(
                        f"{prefix}: module-import: "
                        "wildcard imports are forbidden"
                    )
                elif node.module not in _TYPING_MODULES:
                    name = f"{node.module}.{alias.name}"
                    if not _is_module(name, import_roots):
                        errors.append(
                            f"{prefix}: module-import: "
                            "import the module instead "
                            f"of its member {name!r}; no module path was found"
                        )
        elif isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            if len(node.generators) > 1 or any(
                len(generator.ifs) > 1 for generator in node.generators
            ):
                errors.append(
                    f"{prefix}: simple-comprehension: use at most one for "
                    "clause and one filter"
                )
    return sorted(errors)


def _import_roots(project_root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """Return project and interpreter library roots for static module checks."""
    roots = [project_root]
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_path(key)
        if value:
            root = pathlib.Path(value)
            if root not in roots:
                roots.append(root)
    return tuple(roots)


def check_paths(
    paths: list[pathlib.Path],
    *,
    import_roots: tuple[pathlib.Path, ...],
) -> list[str]:
    """Check explicit files or recursively selected Python source directories.

    Args:
        paths: Files or directories to inspect. Explicit files may omit a .py
            suffix, allowing the CLI launcher to be checked too.
        import_roots: Static module search directories passed to check_source.

    Returns:
        Sorted diagnostics, including missing paths and unreadable UTF-8 files.
        Source text inside strings and comments is not interpreted as code.
    """
    files: set[pathlib.Path] = set()
    errors = []
    for path in paths:
        if path.is_dir():
            files.update(path.rglob("*.py"))
        elif path.is_file():
            files.add(path)
        else:
            errors.append(f"{path}:1: input: path does not exist")
    for path in sorted(files):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{path}:1: input: cannot read UTF-8 source")
            continue
        errors.extend(check_source(source, path, import_roots=import_roots))
    return sorted(errors)


def main() -> int:
    """Run structural checks, returning 0 on success and 1 for violations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=pathlib.Path,
        help="Files or directories; defaults to project Python code and tests",
    )
    args = parser.parse_args()
    project_root = pathlib.Path(__file__).resolve().parents[1]
    paths = args.paths or [project_root / name for name in _DEFAULT_PATHS]
    errors = check_paths(paths, import_roots=_import_roots(project_root))
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Python structural style checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
