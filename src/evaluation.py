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

"""Pure compression measurements and quality gates, without CLI or storage."""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol


class Compressor(Protocol):
    """Small application port implemented by the compression engine."""

    def compress(
        self, command: str, output: str, *, exit_code: int | None = None
    ) -> tuple[str, str, bool]:
        """Compress captured output without executing its command label.

        Args:
            command: Command label used to select a processor.
            output: Captured command output.
            exit_code: Captured command status, or None when unknown.

        Returns:
            The resulting output, processor name, and whether compression ran.
        """


@dataclasses.dataclass(frozen=True)
class QualityPolicy:
    """Limits that report violations without truncating the evaluated output.

    Attributes:
        max_tokens: Maximum estimated output tokens, or None for no limit.
        min_savings_percent: Minimum percentage of characters saved, or None
            for no minimum.
        must_preserve: Nonempty literal strings required in input and output.
    """

    max_tokens: int | None = None
    min_savings_percent: float | None = None
    must_preserve: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate limits and required strings.

        Raises:
            ValueError: A limit or required string has an invalid value or type.
        """
        if self.max_tokens is not None and (
            # A plain integer excludes bool and custom numeric subclasses.
            # pylint: disable-next=unidiomatic-typecheck
            type(self.max_tokens) is not int or self.max_tokens < 0
        ):
            raise ValueError("max_tokens must be a non-negative integer")
        minimum = self.min_savings_percent
        if minimum is not None and (
            isinstance(minimum, bool)
            or not isinstance(minimum, (int, float))
            or not 0 <= minimum <= 100
        ):
            raise ValueError(
                "min_savings_percent must be a number between 0 and 100"
            )
        if not isinstance(self.must_preserve, tuple) or any(
            not isinstance(text, str) or not text for text in self.must_preserve
        ):
            raise ValueError("must_preserve must contain non-empty strings")


@dataclasses.dataclass(frozen=True)
class Evaluation:
    """An immutable compression result and its quality verdict.

    Attributes:
        compressed: Output returned by the compressor, including redactions.
        processor: Name reported by the compressor.
        was_compressed: Whether the compressor accepted a transformed result.
        original_chars: Number of input characters.
        original_tokens: Estimated input tokens, rounded up.
        compressed_tokens: Estimated output tokens, rounded up.
        savings_percent: Percentage of input characters saved.
        chars_per_token: Character-to-token ratio used for both estimates.
        violations: Stable identifiers for failed policy checks.
        policy: Limits and required strings used to evaluate this result.
    """

    compressed: str
    processor: str
    was_compressed: bool
    original_chars: int
    original_tokens: int
    compressed_tokens: int
    savings_percent: float
    chars_per_token: float
    violations: tuple[str, ...]
    policy: QualityPolicy

    def report(self) -> dict:
        """Return measurements and verdict without captured content.

        Returns:
            A JSON-serializable report containing estimates, limit values, and
            violation identifiers. It excludes commands, captured output, and
            the literal strings required by the policy.
        """
        return {
            "processor": self.processor,
            "was_compressed": self.was_compressed,
            "original_chars": self.original_chars,
            "compressed_chars": len(self.compressed),
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "savings_percent": round(self.savings_percent, 2),
            "token_estimate": {
                "method": "ceil(chars / chars_per_token)",
                "chars_per_token": self.chars_per_token,
            },
            "passed": not self.violations,
            "violations": list(self.violations),
            "limits": {
                "max_tokens": self.policy.max_tokens,
                "min_savings_percent": self.policy.min_savings_percent,
                "must_preserve_count": len(self.policy.must_preserve),
            },
        }


def evaluate(
    engine: Compressor,
    command: str,
    output: str,
    *,
    policy: QualityPolicy | None = None,
    exit_code: int | None = None,
    chars_per_token: float = 4,
) -> Evaluation:
    """Measure compression and check user-supplied preservation requirements.

    Args:
        engine: Compressor to invoke once for the captured output.
        command: Command label for routing; this function never executes it.
        output: Captured command output.
        policy: Limits to check, or None to collect measurements without limits.
        exit_code: Captured command status, or None when unknown.
        chars_per_token: Positive, finite character-to-token estimation ratio.

    Returns:
        The compressor's output, estimated savings, and policy verdict. A
        failed policy check does not change or further truncate the output.

    Raises:
        ValueError: chars_per_token is not a positive finite number.
    """
    if (
        isinstance(chars_per_token, bool)
        or not isinstance(chars_per_token, (int, float))
        or chars_per_token <= 0
    ):
        raise ValueError("chars_per_token must be a positive finite number")
    try:
        finite = math.isfinite(chars_per_token)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("chars_per_token must be a positive finite number")
    policy = policy or QualityPolicy()
    compressed, processor, changed = engine.compress(
        command, output, exit_code=exit_code
    )
    original_tokens = math.ceil(len(output) / chars_per_token)
    compressed_tokens = math.ceil(len(compressed) / chars_per_token)
    savings = (
        (len(output) - len(compressed)) / len(output) * 100 if output else 0.0
    )
    violations = []
    if policy.max_tokens is not None and compressed_tokens > policy.max_tokens:
        violations.append("max_tokens")
    if (
        policy.min_savings_percent is not None
        and savings < policy.min_savings_percent
    ):
        violations.append("min_savings_percent")
    for index, text in enumerate(policy.must_preserve):
        if text not in output:
            violations.append(f"must_preserve[{index}]:missing_in_input")
        elif text not in compressed:
            violations.append(f"must_preserve[{index}]:missing_in_output")
    return Evaluation(
        compressed,
        processor,
        changed,
        len(output),
        original_tokens,
        compressed_tokens,
        savings,
        chars_per_token,
        tuple(violations),
        policy,
    )
