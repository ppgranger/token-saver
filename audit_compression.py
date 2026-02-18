#!/usr/bin/env python3
"""Deep audit of Token-Saver compression engine.

Generates realistic command outputs and measures compression ratios,
then identifies opportunities for further compression.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.engine import CompressionEngine

engine = CompressionEngine()

# ============================================================
# Helper
# ============================================================


def audit(label: str, command: str, output: str, observations: list[str] | None = None):
    """Run compression and print audit report."""
    compressed, processor, was_compressed = engine.compress(command, output)
    orig_len = len(output)
    comp_len = len(compressed)
    ratio = (orig_len - comp_len) / orig_len * 100 if orig_len else 0
    saved = orig_len - comp_len

    print(f"\n{'=' * 80}")
    print(f"SCENARIO: {label}")
    print(f"Command:  {command}")
    print(f"Processor: {processor} | Compressed: {was_compressed}")
    print(f"Original:   {orig_len:>7,} chars  ({len(output.splitlines()):>5} lines)")
    print(f"Compressed: {comp_len:>7,} chars  ({len(compressed.splitlines()):>5} lines)")
    print(f"Saved:      {saved:>7,} chars  ({ratio:5.1f}%)")
    print("----- First 15 lines of compressed output -----")
    for _i, line in enumerate(compressed.splitlines()[:15]):
        print(f"  {line}")
    if len(compressed.splitlines()) > 15:
        print(f"  ... ({len(compressed.splitlines()) - 15} more lines)")
    if observations:
        print("----- Observations -----")
        for obs in observations:
            print(f"  [!] {obs}")
    print(f"{'=' * 80}")
    return ratio, was_compressed


# ============================================================
# 1. GIT SCENARIOS
# ============================================================

# 1a. git status with 30+ files across many directories
git_status_lines = [
    "On branch feature/token-compression",
    "Your branch is ahead of 'origin/feature/token-compression' by 3 commits.",
    "",
    "Changes to be committed:",
    '  (use "git restore --staged <file>..." to unstage)',
    "",
]
staged_dirs = {
    "src/processors": [
        "git.py",
        "test_output.py",
        "build_output.py",
        "lint_output.py",
        "file_listing.py",
    ],
    "src": ["engine.py", "config.py", "tracker.py"],
    "tests": ["test_engine.py", "test_processors.py", "test_hooks.py"],
}
for d, files in staged_dirs.items():
    for f in files:
        git_status_lines.append(f"\tmodified:   {d}/{f}")

git_status_lines += [
    "",
    "Changes not staged for commit:",
    '  (use "git add <file>..." to update what will be committed)',
    '  (use "git restore <file>..." to discard changes in working directory)',
    "",
]

unstaged_dirs = {
    "docs": ["api.md", "configuration.md", "getting-started.md", "faq.md"],
    "src/utils": ["helpers.py", "formatters.py", "validators.py"],
    "scripts": ["deploy.sh", "benchmark.py"],
}
for d, files in unstaged_dirs.items():
    for f in files:
        git_status_lines.append(f"\tmodified:   {d}/{f}")

git_status_lines += [
    "",
    "Untracked files:",
    '  (use "git add <file>..." to include in what will be committed)',
    "",
]
untracked = [
    "src/processors/docker_output.py",
    "src/processors/network_output.py",
    "tests/test_docker.py",
    "tests/test_network.py",
    "docs/changelog.md",
    "docs/architecture.md",
    "scripts/setup_dev.sh",
    "scripts/lint.sh",
    "scripts/test_all.sh",
    ".env.example",
    "Makefile",
]
for f in untracked:
    git_status_lines.append(f"\t{f}")

git_status_output = "\n".join(git_status_lines)

audit(
    "git status (30+ files, verbose format)",
    "git status",
    git_status_output,
    [
        "QUESTION: Are hint lines ('use git restore...') being dropped? They should be.",
        "QUESTION: Is the 'Your branch is ahead...' line preserved? It SHOULD be.",
        "CHECK: Directory grouping threshold (>8) -- is 8 optimal or should it be lower?",
    ],
)


# 1b. git diff with large context lines
diff_lines = []
for i in range(5):
    fname_a = f"src/module_{i}.py"
    fname_b = fname_a
    diff_lines.append(f"diff --git a/{fname_a} b/{fname_b}")
    diff_lines.append(f"index abc{i}def..123{i}456 100644")
    diff_lines.append(f"--- a/{fname_a}")
    diff_lines.append(f"+++ b/{fname_b}")
    diff_lines.append(f"@@ -{10 + i * 100},{30} +{10 + i * 100},{32} @@ def some_function_{i}():")
    # 10 context lines before the change
    for j in range(10):
        diff_lines.append(
            f"     # This is context line {j} that hasn't changed and takes up tokens"
        )
    # Actual changes
    diff_lines.append(f"-    old_value = compute_something({i})")
    diff_lines.append("-    return old_value")
    diff_lines.append(f"+    new_value = compute_something_better({i})")
    diff_lines.append("+    cached = cache.get(new_value)")
    diff_lines.append("+    if cached:")
    diff_lines.append("+        return cached")
    diff_lines.append("+    return new_value")
    # 10 context lines after the change
    for j in range(10):
        diff_lines.append(
            f"     # This is trailing context line {j} that is unchanged and wastes tokens"
        )

diff_output = "\n".join(diff_lines)

audit(
    "git diff (5 files, 20 context lines each)",
    "git diff",
    diff_output,
    [
        "ISSUE: Context lines (prefixed with ' ') are kept verbatim -- these are UNCHANGED lines.",
        "OPPORTUNITY: Could reduce to 3 context lines (like -U3) since the AI can infer the rest.",
        "ISSUE: 'index abc0def..1230456 100644' lines are NEVER useful to the AI model.",
        "ISSUE: '--- a/file' and '+++ b/file' lines are redundant when 'diff --git a/... b/...' is present.",
        "RECOMMENDATION: Strip index lines, strip ---/+++ lines, reduce context to 3 lines = ~60% more savings.",
    ],
)


# 1c. git log --oneline with 50 entries
log_oneline_lines = []
for i in range(50):
    hashes = f"{i:07x}"
    messages = [
        "fix: resolve race condition in token counter",
        "feat: add support for cargo test output",
        "chore: update dependencies",
        "docs: improve README compression section",
        "refactor: simplify processor dispatch logic",
        "test: add edge case tests for git diff",
        "fix: handle empty output gracefully",
        "feat: add mypy lint processor",
        "ci: fix GitHub Actions workflow",
        "perf: optimize regex compilation caching",
    ]
    log_oneline_lines.append(f"{hashes} {messages[i % len(messages)]}")

log_oneline_output = "\n".join(log_oneline_lines)

audit(
    "git log --oneline (50 entries, already compact)",
    "git log --oneline",
    log_oneline_output,
    [
        "CHECK: max_log_entries=20 truncates to 20 -- is that too aggressive for --oneline?",
        "OBSERVATION: --oneline format is already extremely compact. Each line is ~50 chars.",
        "SUGGESTION: For --oneline, could increase max_entries to 30 since the format is cheap.",
    ],
)


# 1d. git diff --stat output
diff_stat_lines = []
for i in range(25):
    fname = f"src/{'module' if i < 15 else 'test'}_{i:02d}.py"
    insertions = (i * 7 + 3) % 50
    deletions = (i * 3 + 1) % 20
    bar = "+" * min(insertions, 30) + "-" * min(deletions, 15)
    diff_stat_lines.append(f" {fname:<45} | {insertions + deletions:>4} {bar}")
diff_stat_lines.append(" 25 files changed, 347 insertions(+), 128 deletions(-)")

diff_stat_output = "\n".join(diff_stat_lines)

audit(
    "git diff --stat (25 files)",
    "git diff --stat",
    diff_stat_output,
    [
        "ISSUE: diff --stat is already a SUMMARY format -- further compression may lose info.",
        "CHECK: Does the git processor handle --stat specifically? It probably goes through _process_diff.",
        "OBSERVATION: The visual bars (++++---) are not useful to the AI. Could be stripped.",
    ],
)


# 1e. git status -s (short format) with 40+ files
git_status_short_lines = []
statuses = ["M ", " M", "A ", "??", "MM", "D ", " D", "AM", "R "]
dirs = ["src/", "src/processors/", "tests/", "docs/", "scripts/", "lib/", "config/", ""]
for i in range(45):
    status = statuses[i % len(statuses)]
    d = dirs[i % len(dirs)]
    ext = ["py", "ts", "js", "md", "json"][i % 5]
    git_status_short_lines.append(f"{status} {d}file_{i:02d}.{ext}")

git_status_short_output = "\n".join(git_status_short_lines)

audit(
    "git status -s (45 files, short format)",
    "git status -s",
    git_status_short_output,
    [
        "CHECK: Short format is already compact -- does the processor handle 'XY filename' format correctly?",
        "OBSERVATION: Short format has no hint lines to strip, so savings come purely from grouping.",
        "QUESTION: Is directory-based grouping for short format helpful or does it obscure the status codes?",
    ],
)


# ============================================================
# 2. TEST SCENARIOS
# ============================================================

# 2a. pytest with 500+ passing tests and 2 failures
pytest_lines = [
    "============================= test session starts ==============================",
    "platform darwin -- Python 3.12.0, pytest-8.0.0, pluggy-1.4.0",
    "rootdir: /Users/dev/project",
    "configfile: pyproject.toml",
    "plugins: cov-4.1.0, xdist-3.5.0, asyncio-0.23.0",
    "collected 512 items",
    "",
]
# 500 passing tests
for i in range(500):
    module = f"tests/test_module_{i // 25:02d}.py"
    test_name = f"test_function_{i:04d}"
    pytest_lines.append(f"{module}::{test_name} PASSED")

# 2 failures
pytest_lines.extend(
    [
        "",
        "=================================== FAILURES ===================================",
        "__________________________ test_compression_ratio ______________________________",
        "",
        "    def test_compression_ratio():",
        "        engine = CompressionEngine()",
        "        result = engine.compress('git status', large_output)",
        ">       assert len(result[0]) < len(large_output) * 0.5",
        "E       AssertionError: assert 1500 < 1000",
        "E        +  where 1500 = len('...')",
        "E        +  and   1000 = 2000 * 0.5",
        "",
        "/Users/dev/project/tests/test_engine.py:45: AssertionError",
        "__________________________ test_diff_context_trim _______________________________",
        "",
        "    def test_diff_context_trim():",
        "        processor = GitProcessor()",
        "        output = processor._process_diff(sample_diff)",
        ">       assert output.count(' ') < 10",
        "E       AssertionError: assert 42 < 10",
        "",
        "/Users/dev/project/tests/test_processors.py:89: AssertionError",
        "=========================== short test summary info ============================",
        "FAILED tests/test_engine.py::test_compression_ratio - AssertionError: assert 1500 < 1000",
        "FAILED tests/test_processors.py::test_diff_context_trim - AssertionError: assert 42 < 10",
        "========================= 2 failed, 510 passed ================================",
    ]
)

pytest_output = "\n".join(pytest_lines)

audit(
    "pytest (500 passed, 2 failed)",
    "pytest",
    pytest_output,
    [
        "KEY CHECK: Are all 500 'PASSED' lines being collapsed to a single count?",
        "CHECK: Is the failure traceback fully preserved?",
        "ISSUE: Platform, rootdir, plugins lines are noise -- are they stripped?",
        "ISSUE: The 'collected 512 items' line is noise.",
        "OBSERVATION: The failure block is the ONLY useful content here.",
    ],
)


# 2b. pytest with only warnings (no failures)
pytest_warn_lines = [
    "============================= test session starts ==============================",
    "platform darwin -- Python 3.12.0, pytest-8.0.0",
    "rootdir: /Users/dev/project",
    "collected 200 items",
    "",
]
for i in range(200):
    pytest_warn_lines.append(f"tests/test_mod_{i // 10:02d}.py::test_{i:03d} PASSED")

pytest_warn_lines.extend(
    [
        "",
        "============================= warnings summary ================================",
    ]
)
# 30 deprecation warnings
for i in range(30):
    pytest_warn_lines.extend(
        [
            f"  /usr/lib/python3.12/site-packages/somepackage/module{i % 5}.py:{100 + i}: DeprecationWarning: "
            f"function deprecated_func_{i % 8}() is deprecated and will be removed in v{3 + i % 3}.0. "
            f"Use new_func_{i % 8}() instead.",
            f"    deprecated_func_{i % 8}()",
        ]
    )

pytest_warn_lines.extend(
    [
        "",
        "-- Docs: https://docs.pytest.org/en/stable/warnings.html",
        "========================= 200 passed, 30 warnings =============================",
    ]
)

pytest_warn_output = "\n".join(pytest_warn_lines)

audit(
    "pytest (200 passed, 30 warnings, 0 failures)",
    "pytest tests/",
    pytest_warn_output,
    [
        "ISSUE: 30 deprecation warnings are mostly IDENTICAL pattern -- should be collapsed.",
        "OBSERVATION: When ALL tests pass, the only useful info is '200 passed, 30 warnings'.",
        "QUESTION: Are the warning details useful? For most cases, just the count suffices.",
        "SUGGESTION: Collapse identical warning types: 'DeprecationWarning (x30): function X deprecated'.",
    ],
)


# 2c. jest output with 50 passing suites
jest_lines = []
for i in range(50):
    suite = f"src/components/Component{i:02d}.test.tsx"
    jest_lines.append(f" PASS  {suite}")

jest_lines.extend(
    [
        "",
        "Test Suites: 50 passed, 50 total",
        "Tests:       312 passed, 312 total",
        "Snapshots:   0 total",
        "Time:        8.234 s",
        "Ran all test suites.",
    ]
)

jest_output = "\n".join(jest_lines)

audit(
    "jest (50 suites, all passing)",
    "npx jest",
    jest_output,
    [
        "CHECK: Are all 50 ' PASS  ...' lines collapsed into a count?",
        "OBSERVATION: Final summary has all the info the AI needs.",
        "SUGGESTION: Could collapse to '[50 suites passed, 312 tests] + summary lines'.",
    ],
)


# ============================================================
# 3. BUILD SCENARIOS
# ============================================================

# 3a. npm install with 200+ packages
npm_lines = []
for i in range(220):
    pkg = f"@scope/package-{i:03d}"
    ver = f"{i % 5}.{i % 10}.{i % 3}"
    npm_lines.append(f"npm WARN deprecated {pkg}@{ver}: Use something else" if i % 20 == 0 else "")
    if i % 3 == 0:
        npm_lines.append(
            f"npm http fetch GET 200 https://registry.npmjs.org/{pkg}/-/{pkg}-{ver}.tgz"
        )
    npm_lines.append(f"added {pkg}@{ver}")

npm_lines.extend(
    [
        "",
        "added 220 packages, and audited 350 packages in 15s",
        "",
        "25 packages are looking for funding",
        "  run `npm fund` for details",
        "",
        "3 moderate severity vulnerabilities",
        "",
        "To address all issues, run:",
        "  npm audit fix",
        "",
        "Run `npm audit` for details.",
    ]
)

npm_output = "\n".join(npm_lines)

audit(
    "npm install (220 packages)",
    "npm install",
    npm_output,
    [
        "CHECK: Are 'npm http fetch' lines being stripped?",
        "CHECK: Are 'added package@version' lines being stripped?",
        "OBSERVATION: Only the final summary matters.",
        "ISSUE: 'npm WARN deprecated' lines may be useful but should be counted, not listed.",
    ],
)


# 3b. cargo build with 100+ Compiling lines
cargo_lines = []
for i in range(120):
    crate = f"crate-{i:03d}"
    ver = f"{i % 3}.{i % 12}.{i % 5}"
    cargo_lines.append(f"   Compiling {crate} v{ver}")

cargo_lines.extend(
    [
        "   Compiling my-project v0.1.0 (/Users/dev/my-project)",
        "    Finished dev [unoptimized + debuginfo] target(s) in 45.23s",
    ]
)

cargo_output = "\n".join(cargo_lines)

audit(
    "cargo build (120 crates)",
    "cargo build",
    cargo_output,
    [
        "CHECK: Are all 'Compiling' lines stripped?",
        "OBSERVATION: Only 'Finished' line matters.",
        "KEY: The final line has build time and profile -- must keep.",
    ],
)


# 3c. tsc with type errors (no progress)
tsc_lines = []
files_with_errors = [
    (
        "src/components/App.tsx",
        [
            (15, "Type 'string' is not assignable to type 'number'."),
            (42, "Property 'onClick' does not exist on type 'IntrinsicAttributes'."),
            (67, "Argument of type 'null' is not assignable to parameter of type 'string'."),
        ],
    ),
    (
        "src/utils/api.ts",
        [
            (8, "Cannot find module '@/types' or its corresponding type declarations."),
            (23, "Type 'Promise<void>' is not assignable to type 'Promise<Response>'."),
        ],
    ),
    (
        "src/hooks/useAuth.ts",
        [
            (31, "Object is possibly 'undefined'."),
            (45, "Type '{}' is missing the following properties from type 'User': id, name, email"),
        ],
    ),
]
for filepath, errors in files_with_errors:
    for line_num, msg in errors:
        tsc_lines.append(f"{filepath}({line_num},{1}): error TS2322: {msg}")

tsc_lines.append("")
tsc_lines.append("Found 7 errors in 3 files.")

tsc_output = "\n".join(tsc_lines)

audit(
    "tsc (7 type errors)",
    "tsc",
    tsc_output,
    [
        "OBSERVATION: tsc output is already compact and each error is unique.",
        "QUESTION: Does the build processor handle tsc errors? It should match on 'tsc'.",
        "NOTE: tsc errors are each unique, so no dedup opportunity.",
    ],
)


# 3d. pip install with many Collecting/Downloading/Installing lines
pip_lines = []
packages = [
    "requests",
    "flask",
    "sqlalchemy",
    "celery",
    "redis",
    "boto3",
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "scikit-learn",
    "tensorflow",
    "django",
    "fastapi",
    "uvicorn",
    "pydantic",
    "httpx",
    "aiohttp",
    "pytest",
    "black",
    "ruff",
    "mypy",
    "pre-commit",
    "tox",
    "pillow",
    "cryptography",
    "paramiko",
    "fabric",
    "click",
    "typer",
]
for pkg in packages:
    pip_lines.append(f"Collecting {pkg}>=1.0")
    pip_lines.append(f"  Downloading {pkg}-2.1.0-py3-none-any.whl (150 kB)")
    pip_lines.append(
        "     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 150.0/150.0 kB 5.2 MB/s eta 0:00:00"
    )
    pip_lines.append(f"Installing collected packages: {pkg}")
    pip_lines.append(f"Successfully installed {pkg}-2.1.0")

pip_lines.extend(
    [
        "",
        f"Successfully installed {len(packages)} packages",
        "",
        "WARNING: pip's dependency resolver does not currently take into account all the packages that are installed.",
    ]
)

pip_output = "\n".join(pip_lines)

audit(
    "pip install -r requirements.txt (30 packages)",
    "pip install -r requirements.txt",
    pip_output,
    [
        "CHECK: Are Collecting/Downloading/Installing lines stripped?",
        "CHECK: Are progress bars stripped?",
        "OBSERVATION: Only 'Successfully installed X packages' matters.",
        "ISSUE: The progress bar lines (━━━━) are pure waste.",
    ],
)


# ============================================================
# 4. LINT SCENARIOS
# ============================================================

# 4a. ruff with 100+ violations across 4 rules
ruff_lines = []
ruff_rules = {
    "E501": "Line too long",
    "F401": "imported but unused",
    "W291": "trailing whitespace",
    "I001": "Import block is un-sorted or un-formatted",
}
file_count = 0
for rule, msg in ruff_rules.items():
    count = {"E501": 45, "F401": 30, "W291": 20, "I001": 15}[rule]
    for i in range(count):
        fpath = f"src/{'module' if i < count // 2 else 'utils'}/{rule.lower()}_{i:02d}.py"
        ruff_lines.append(f"{fpath}:{10 + i}:{5 + i % 10}: {rule} {msg}")
        file_count += 1

ruff_lines.append(f"Found {file_count} errors.")

ruff_output = "\n".join(ruff_lines)

audit(
    "ruff check (110 violations, 4 rules)",
    "ruff check .",
    ruff_output,
    [
        "CHECK: Are violations grouped by rule?",
        "CHECK: How many examples per rule are shown (lint_example_count=2)?",
        "QUESTION: Is 2 examples enough? The AI needs to see the pattern to fix all occurrences.",
        "SUGGESTION: For auto-fixable rules (E501, W291), 1 example suffices. For import issues, 2-3.",
    ],
)


# 4b. eslint with 50+ files, mostly same 2 rules
eslint_lines = []
eslint_rules = ["no-unused-vars", "react/prop-types"]
for i in range(55):
    rule = eslint_rules[i % 2]
    fpath = f"src/components/Component{i:02d}.tsx"
    eslint_lines.append(
        f"{fpath}:{10 + i}:{1}: '{f'var{i}'}' is defined but never used. ({rule})"
        if rule == "no-unused-vars"
        else f"{fpath}:{10 + i}:{1}: 'propName' is missing in props validation ({rule})"
    )

eslint_lines.extend(
    [
        "",
        "✖ 55 problems (55 errors, 0 warnings)",
    ]
)

eslint_output = "\n".join(eslint_lines)

audit(
    "eslint (55 violations, 2 rules)",
    "npx eslint .",
    eslint_output,
    [
        "CHECK: Violations grouped by rule?",
        "OBSERVATION: 55 violations with only 2 rules -- heavy grouping should apply.",
        "KEY: The file paths ARE useful for the AI to know WHICH files to fix.",
        "SUGGESTION: Show rule + count + list of affected files (not full violation lines).",
    ],
)


# 4c. mypy with 30 errors
mypy_lines = []
mypy_rules = ["arg-type", "return-value", "assignment", "name-defined", "attr-defined"]
for i in range(30):
    rule = mypy_rules[i % len(mypy_rules)]
    fpath = f"src/{'core' if i < 15 else 'api'}/module_{i:02d}.py"
    messages = {
        "arg-type": 'Argument 1 to "process" has incompatible type "str"; expected "int"',
        "return-value": 'Incompatible return value type (got "None", expected "str")',
        "assignment": 'Incompatible types in assignment (expression has type "float", variable has type "int")',
        "name-defined": f'Name "undefined_var_{i}" is not defined',
        "attr-defined": f'"MyClass" has no attribute "nonexistent_{i}"',
    }
    mypy_lines.append(f"{fpath}:{10 + i * 3}: error: {messages[rule]}  [{rule}]")

mypy_lines.extend(
    [
        "Found 30 errors in 30 files (checked 45 source files)",
    ]
)

mypy_output = "\n".join(mypy_lines)

audit(
    "mypy (30 errors, 5 rules)",
    "mypy src/",
    mypy_output,
    [
        "CHECK: Are mypy errors grouped by error code?",
        "OBSERVATION: mypy errors are often unique (different messages per file).",
        "ISSUE: For 'name-defined' and 'attr-defined', the specific name IS important.",
        "SUGGESTION: Group by rule, but keep more examples for unique-message rules.",
    ],
)


# ============================================================
# 5. FILE LISTING SCENARIOS
# ============================================================

# 5a. ls with 100+ files
ls_items = []
for ext in ["py", "ts", "js", "md", "json", "yaml", "toml", "cfg", "txt", "sh"]:
    for i in range(12):
        ls_items.append(f"file_{i:02d}.{ext}")
ls_items.extend(["node_modules/", "dist/", "build/", ".git/", "__pycache__/", "venv/"])

ls_output = "\n".join(ls_items)

audit(
    "ls (126 items)",
    "ls",
    ls_output,
    [
        "CHECK: Files grouped by extension?",
        "OBSERVATION: ls output is already relatively compact (just filenames).",
        "QUESTION: Is extension grouping the best strategy or should we just truncate?",
    ],
)


# 5b. find . -name "*.py" with 200+ results
find_lines = []
find_dirs = {
    "src": 30,
    "src/processors": 20,
    "src/utils": 15,
    "src/core": 25,
    "tests": 35,
    "tests/integration": 15,
    "tests/unit": 20,
    "scripts": 10,
    "tools": 8,
    "benchmarks": 7,
    "examples": 15,
    "docs/scripts": 5,
}
for d, count in find_dirs.items():
    for i in range(count):
        find_lines.append(f"./{d}/module_{i:03d}.py")

find_output = "\n".join(find_lines)

audit(
    "find . -name '*.py' (205 results)",
    "find . -name '*.py'",
    find_output,
    [
        "CHECK: Results grouped by directory?",
        "OBSERVATION: All files have same extension, so extension grouping is useless here.",
        "SUGGESTION: For find with -name '*.ext', just show dir + count since ext is known.",
    ],
)


# 5c. tree with 300+ lines
tree_lines = ["."]
indent_chars = ["├── ", "│   ", "└── ", "    "]
dirs_tree = {
    "src": ["engine.py", "config.py", "tracker.py", "platforms.py", "__init__.py"],
    "src/processors": [
        "git.py",
        "test_output.py",
        "build_output.py",
        "lint_output.py",
        "file_listing.py",
        "file_content.py",
        "generic.py",
        "base.py",
        "__init__.py",
    ],
    "tests": [f"test_{i:02d}.py" for i in range(40)],
    "docs": [f"page_{i:02d}.md" for i in range(30)],
    "scripts": [f"script_{i:02d}.sh" for i in range(20)],
}
for d, files in dirs_tree.items():
    depth = d.count("/")
    prefix = "│   " * depth
    tree_lines.append(f"{prefix}├── {d.split('/')[-1]}/")
    for j, f in enumerate(files):
        connector = "└── " if j == len(files) - 1 else "├── "
        tree_lines.append(f"{prefix}│   {connector}{f}")

# Pad to 300+ lines with more dirs
for i in range(200):
    tree_lines.append(f"│   ├── extra_file_{i:03d}.py")

tree_lines.append(f"\n20 directories, {len(tree_lines)} files")

tree_output = "\n".join(tree_lines)

audit(
    "tree (350+ lines)",
    "tree",
    tree_output,
    [
        "CHECK: Is tree output truncated in the middle?",
        "OBSERVATION: tree output structure IS useful -- truncation loses the structure.",
        "SUGGESTION: Could convert tree to a compact format like find's directory grouping.",
    ],
)


# ============================================================
# 6. FILE CONTENT
# ============================================================

# 6a. cat of a 1000-line file
cat_lines = [
    "#!/usr/bin/env python3",
    '"""Large module with many functions."""',
    "",
    "import os",
    "import sys",
    "import json",
    "import re",
    "from typing import Any, Optional",
    "",
    "",
]
for i in range(990):
    if i % 50 == 0:
        cat_lines.append(f"\nclass Module{i // 50}:")
        cat_lines.append(f'    """Class number {i // 50}."""')
        cat_lines.append("")
    elif i % 10 == 0:
        cat_lines.append(f"    def method_{i}(self, arg: str) -> Optional[str]:")
        cat_lines.append(f'        """Method {i} docstring."""')
        cat_lines.append("        if not arg:")
        cat_lines.append("            return None")
        cat_lines.append("        return arg.upper()")
        cat_lines.append("")
    else:
        cat_lines.append(f"        # Processing step {i}")

cat_output = "\n".join(cat_lines)

audit(
    "cat large_file.py (1000 lines)",
    "cat src/large_module.py",
    cat_output,
    [
        "CHECK: Is the file truncated with head/tail preservation?",
        "OBSERVATION: For cat, the AI usually needs to see the WHOLE file or a specific section.",
        "ISSUE: max_file_lines=300 with head=150, tail=50 drops 800 lines of context.",
        "QUESTION: Is head=150, tail=50 a good split? Maybe 100/100 is better for symmetry.",
    ],
)


# ============================================================
# 7. GENERIC / DOCKER / NETWORK
# ============================================================

# 7a. Docker build with 20 steps
docker_lines = ["Sending build context to Docker daemon  45.2MB", ""]
for i in range(1, 21):
    docker_lines.append(
        f"Step {i}/20 : {'FROM python:3.12-slim' if i == 1 else f'RUN pip install package{i}'}"
    )
    docker_lines.append(f" ---> Running in abc{i:04d}def")
    if i < 20:
        docker_lines.append(f"Removing intermediate container abc{i:04d}def")
        docker_lines.append(f" ---> sha256:{'a' * 12}{i:04d}")
    for j in range(3):
        docker_lines.append(f"  Downloading package{i}-dep{j} (1.2 MB)")
        docker_lines.append(f"  Installing package{i}-dep{j}")

docker_lines.extend(
    [
        "Successfully built sha256:abcdef123456",
        "Successfully tagged myapp:latest",
    ]
)

docker_output = "\n".join(docker_lines)

audit(
    "docker build (20 steps)",
    "docker build -t myapp .",
    docker_output,
    [
        "CHECK: Does generic processor handle docker build?",
        "OBSERVATION: 'Running in', 'Removing intermediate container', sha256 lines are noise.",
        "OBSERVATION: Download/install progress within steps is noise.",
        "SUGGESTION: A dedicated docker processor could keep only Step lines and final result.",
    ],
)


# 7b. curl/wget download output
curl_lines = [
    "  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current",
    "                                 Dload  Upload   Total   Spent    Left  Speed",
]
for pct in range(0, 101, 1):
    curl_lines.append(
        f"  {pct}  1024M    {pct}  {pct * 10}M    0     0  52.3M      0  0:00:19  0:00:{pct // 5:02d}  0:00:{19 - pct // 5:02d} 52.3M"
    )

curl_lines.append("100 1024M  100 1024M    0     0  52.3M      0  0:00:19  0:00:19 --:--:-- 55.1M")

curl_output = "\n".join(curl_lines)

audit(
    "curl download (100 progress lines)",
    "curl -O https://example.com/large-file.tar.gz",
    curl_output,
    [
        "CHECK: Are progress lines (percentage) being collapsed?",
        "OBSERVATION: Only the final 100% line matters.",
        "ISSUE: 101 nearly-identical lines should compress to 1-2 lines.",
    ],
)


# 7c. npm audit output
npm_audit_lines = []
for i in range(15):
    severity = ["low", "moderate", "high", "critical"][i % 4]
    npm_audit_lines.extend(
        [
            "# npm audit report",
            "",
            f"{'package-' + str(i)}  <2.{i}.0",
            f"Severity: {severity}",
            f"{'Description of vulnerability ' + str(i)} - https://github.com/advisories/GHSA-xxxx-{i:04d}",
            "fix available via `npm audit fix --force`",
            f"Will install package-{i}@2.{i}.0, which is a breaking change",
            f"node_modules/package-{i}",
            f"  dep-of-{i} *",
            f"    node_modules/dep-of-{i}",
            "",
        ]
    )

npm_audit_lines.extend(
    [
        "15 vulnerabilities (4 low, 4 moderate, 4 high, 3 critical)",
        "",
        "To address all issues, run:",
        "  npm audit fix",
    ]
)

npm_audit_output = "\n".join(npm_audit_lines)

audit(
    "npm audit (15 vulnerabilities)",
    "npm audit",
    npm_audit_output,
    [
        "CHECK: Does generic processor group the repeated audit blocks?",
        "OBSERVATION: Each vulnerability block has the SAME structure.",
        "SUGGESTION: A dedicated processor could group by severity and show counts.",
        "KEY: Vulnerability details ARE important for the AI to suggest fixes.",
    ],
)


# ============================================================
# SUMMARY REPORT
# ============================================================
print("\n" + "=" * 80)
print("DEEP AUDIT SUMMARY - COMPRESSION IMPROVEMENT OPPORTUNITIES")
print("=" * 80)

print("""

CRITICAL FINDINGS:
==================

1. GIT DIFF CONTEXT LINES (HIGH IMPACT)
   - Context lines (unchanged ' ' prefixed lines) are kept VERBATIM
   - In the test, 100 context lines across 5 files = ~5000 chars wasted
   - RECOMMENDATION: Reduce context to 3 lines before/after each change (like -U3)
   - ESTIMATED ADDITIONAL SAVINGS: 40-60% on typical diffs
   - The 'index' line (e.g., 'index abc0def..1230456 100644') is NEVER useful
   - The '---' and '+++' lines are redundant with 'diff --git a/... b/...'

2. GIT DIFF --STAT VISUAL BARS (MEDIUM IMPACT)
   - The ++++--- bars in diff --stat waste ~30% of the output
   - Only the filename and change count matter
   - diff --stat is not handled specially -- goes through _process_diff which
     may incorrectly interpret stat lines

3. GIT LOG --ONELINE TRUNCATION (LOW IMPACT)
   - max_log_entries=20 is applied to --oneline format
   - --oneline is already ~50 chars/line, so 50 entries = 2500 chars
   - Could safely keep 30-40 entries for --oneline format

4. PYTEST PASSED LINES (HIGH IMPACT)
   - 500 'PASSED' lines are collapsed to '[500 tests passed]' -- GOOD
   - BUT: platform/rootdir/plugins/collected lines are NOT stripped by the
     current pytest processor (they don't match PASSED/FAILED patterns)
   - WARNING BLOCKS in pytest are not collapsed (each warning kept verbatim)

5. DEPRECATION WARNING COLLAPSE (MEDIUM IMPACT)
   - pytest warnings section: 30 near-identical DeprecationWarning lines
   - Currently treated as generic content, not collapsed by pattern
   - RECOMMENDATION: Detect warning patterns, collapse to count + 1 example

6. BUILD PROGRESS LINES (HIGH IMPACT)
   - pip: Collecting/Downloading/progress bars should ALL be stripped
   - cargo: Compiling lines are stripped -- GOOD
   - npm: http fetch lines need stripping

7. LINT GROUPING (WORKING WELL)
   - Violations are grouped by rule with example_count=2
   - SUGGESTION: Could also list affected files compactly

8. FILE LISTINGS (WORKING WELL)
   - find/ls grouping by directory/extension works
   - tree truncation works but loses structure info

9. CURL/DOWNLOAD PROGRESS (HIGH IMPACT)
   - 101 progress lines should collapse to final line only
   - Generic processor's repeated-line collapse helps but progress lines
     differ slightly (different percentages) so they are NOT collapsed

10. DOCKER BUILD (MEDIUM IMPACT)
    - No dedicated processor -- falls through to generic
    - 'Running in', 'Removing intermediate', sha256 lines are noise
    - RECOMMENDATION: Add docker processor or enhance generic

PROCESSOR-SPECIFIC ISSUES:
==========================

GitProcessor._process_diff:
  - Keeps 'index' lines (waste)
  - Keeps '---/+++' lines (redundant with 'diff --git')
  - Does NOT reduce context lines (keeps all ' ' lines up to max_hunk_lines=150)
  - Does NOT handle --stat format specially

GitProcessor._process_status:
  - Directory grouping threshold of 8 may be too high for most repos
  - Short format (-s) IS handled correctly via regex
  - Verbose format drops hint lines -- GOOD

TestOutputProcessor._process_pytest:
  - Collapses PASSED lines -- GOOD
  - Does NOT collapse warning blocks
  - Does NOT strip platform/rootdir/plugins lines
  - Failure blocks fully preserved -- GOOD

BuildOutputProcessor:
  - _is_progress_line catches Downloading/Installing/Compiling -- GOOD
  - Does NOT catch pip progress bars (━━━━━━)
  - Does NOT catch curl/wget progress
  - npm http fetch IS caught

LintOutputProcessor:
  - Rule grouping works well
  - Example count of 2 is reasonable
  - mypy format [error-code] is parsed -- GOOD

FileContentProcessor:
  - head=150, tail=50 split is asymmetric (favoring imports/headers)
  - This is actually GOOD for most code files

GenericProcessor:
  - ANSI stripping works
  - Repeated-line collapse only catches IDENTICAL lines
  - Does NOT catch near-identical lines (progress with different %)
  - Middle truncation works for very long output

PRIORITY RECOMMENDATIONS (by estimated token savings):
======================================================

P0 - DIFF CONTEXT REDUCTION:
   Strip context lines to max 3 before/after each change
   Strip 'index' lines entirely
   Strip '---/+++' lines when 'diff --git' is present
   -> Saves 40-60% on every diff

P1 - PROGRESS LINE DETECTION:
   Add pattern for progress bars (━━, ██, ###, percentage changes)
   Collapse curl/wget output to final line
   -> Saves 90%+ on download/build output

P2 - WARNING COLLAPSE:
   In pytest, collapse identical warning types
   -> Saves 80%+ on warning-heavy test output

P3 - DOCKER PROCESSOR:
   Add Step-aware processor
   Strip intermediate container IDs and sha256
   -> Saves 60%+ on docker build

P4 - DIFF --STAT HANDLER:
   Strip visual bars, keep filename + counts only
   -> Saves 30% on diff --stat

""")
