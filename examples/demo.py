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

"""Process example fixtures through the compression engine and display results.

This script generates the data for the README hero table by running each
fixture through the actual compression engine and reporting stats.

Usage:
    python3 examples/demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Run the example directly without installing the package first.
# pylint: disable=wrong-import-position
import src.engine
from src import config

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
CHARS_PER_TOKEN = config.get("chars_per_token")

engine = src.engine.CompressionEngine()

DEMOS = [
    ("git diff (large refactor)", "git diff", "large_git_diff.txt"),
    ("pytest (50 pass, 2 fail)", "pytest", "pytest_output.txt"),
    ("terraform plan (15 resources)", "terraform plan", "terraform_plan.txt"),
    ("npm install (80 packages)", "npm install", "npm_install.txt"),
    ("kubectl get pods (50 pods)", "kubectl get pods -A", "kubectl_pods.txt"),
]


def to_tokens(n: int) -> int:
    """Estimate tokens from characters using the configured ratio."""
    return max(1, round(n / CHARS_PER_TOKEN)) if n > 0 else 0


def main() -> None:
    """Print a before-and-after comparison for each bundled output fixture."""
    print()
    print("Token-Saver Compression Demo")
    print("=" * 80)
    print()

    total_orig = 0
    total_comp = 0

    for label, command, fixture_file in DEMOS:
        fixture_path = os.path.join(FIXTURES_DIR, fixture_file)
        if not os.path.exists(fixture_path):
            print(f"  [SKIP] {fixture_file} not found")
            continue

        with open(fixture_path, encoding="utf-8") as f:
            raw_output = f.read()

        compressed, processor, was_compressed = engine.compress(
            command, raw_output
        )

        orig_chars = len(raw_output)
        comp_chars = len(compressed)
        orig_tokens = to_tokens(orig_chars)
        comp_tokens = to_tokens(comp_chars)
        savings_pct = (
            (orig_chars - comp_chars) / orig_chars * 100
            if orig_chars > 0
            else 0
        )

        total_orig += orig_chars
        total_comp += comp_chars

        status = "compressed" if was_compressed else "unchanged"
        print(f"  {label}")
        print(f"    Processor:  {processor}")
        print(
            f"    Original:   {orig_tokens:>6,} tokens ({orig_chars:>8,} chars)"
        )
        print(
            f"    Compressed: {comp_tokens:>6,} tokens ({comp_chars:>8,} chars)"
        )
        print(f"    Savings:    {savings_pct:5.1f}%  [{status}]")
        print()

    if total_orig > 0:
        total_savings = (total_orig - total_comp) / total_orig * 100
        print("-" * 80)
        print(
            f"  Total: {to_tokens(total_orig):,} -> "
            f"{to_tokens(total_comp):,} tokens"
            f"  ({total_savings:.1f}% overall savings)"
        )
    print()


if __name__ == "__main__":
    main()
