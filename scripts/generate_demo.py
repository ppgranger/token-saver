#!/usr/bin/env python3
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

"""Generate before/after compression demo for screenshots.

Processes example fixtures through the compression engine and prints
a side-by-side comparison showing original vs compressed sizes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The demo can run directly from an unpacked repository.
# pylint: disable=wrong-import-position
import src.engine
from src import config

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "fixtures"
)
CHARS_PER_TOKEN = config.get("chars_per_token")

engine = src.engine.CompressionEngine()


def to_tokens(n: int) -> int:
    """Estimate tokens from characters using the configured ratio."""
    return max(1, round(n / CHARS_PER_TOKEN)) if n > 0 else 0


def format_tokens(n: int) -> str:
    """Format a token estimate using a compact thousands suffix."""
    if n >= 1000:
        return f"{n / 1000:,.1f}k"
    return str(n)


def demo_fixture(label: str, command: str, fixture_file: str) -> None:
    """Process a fixture and print the comparison."""
    fixture_path = os.path.join(FIXTURES_DIR, fixture_file)
    if not os.path.exists(fixture_path):
        print(f"  [SKIP] {fixture_file} not found")
        return

    with open(fixture_path, encoding="utf-8") as f:
        raw_output = f.read()

    compressed, processor, _ = engine.compress(command, raw_output)

    orig_chars = len(raw_output)
    comp_chars = len(compressed)
    orig_tokens = to_tokens(orig_chars)
    comp_tokens = to_tokens(comp_chars)
    savings_pct = (
        (orig_chars - comp_chars) / orig_chars * 100 if orig_chars > 0 else 0
    )

    print(
        f"  {label:<35} {orig_tokens:>8} tokens -> {comp_tokens:>8} tokens   "
        f"{savings_pct:5.1f}%  [{processor}]"
    )


def main() -> None:
    """Render the bundled fixture comparisons as a terminal demo."""
    print()
    print("Token-Saver Compression Demo")
    print("=" * 78)
    print()
    print(
        f"  {'Command':<35} {'Raw':>14}    {'Compressed':>14}   "
        f"{'Saved':>6}  Processor"
    )
    print(f"  {'-' * 35} {'-' * 14}    {'-' * 14}   {'-' * 6}  {'-' * 10}")

    demo_fixture("git diff (large refactor)", "git diff", "large_git_diff.txt")
    demo_fixture("pytest (50 pass, 2 fail)", "pytest", "pytest_output.txt")
    demo_fixture(
        "terraform plan (15 resources)", "terraform plan", "terraform_plan.txt"
    )
    demo_fixture("npm install (80 packages)", "npm install", "npm_install.txt")
    demo_fixture(
        "kubectl get pods (50 pods)", "kubectl get pods", "kubectl_pods.txt"
    )

    print()
    print("=" * 78)
    print()
    print("To generate terminal screenshots from this output:")
    print("  1. Run: python3 scripts/generate_demo.py")
    print("  2. Take a screenshot of the terminal output")
    print()


if __name__ == "__main__":
    main()
