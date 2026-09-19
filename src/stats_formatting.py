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

"""Pure statistics presentation, independent of storage and configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def estimate_tokens(characters: int, chars_per_token: float) -> int:
    """Estimate tokens from a character count using an explicit conversion.

    Args:
        characters: Number of captured or saved characters.
        chars_per_token: Positive, validated characters-per-token estimate.

    Returns:
        Rounded token estimate, at least one for positive character counts and
        zero otherwise. This is not measured model usage or billing data.
    """
    return max(1, round(characters / chars_per_token)) if characters > 0 else 0


def format_tokens(tokens: int) -> str:
    """Format token estimates for the historical session-start message.

    Args:
        tokens: Estimated token count to display.

    Returns:
        Human-readable count with a k/M suffix where appropriate and a unit.
    """
    if tokens < 1_000:
        return f"{tokens} tokens"
    if tokens < 1_000_000:
        return f"{tokens / 1_000:.1f}k tokens"
    return f"{tokens / 1_000_000:.1f}M tokens"


def format_stats_message(
    lifetime: Mapping[str, int | float],
    session: Mapping[str, int | float],
    *,
    chars_per_token: float,
) -> str:
    """Render the session-start message from already queried statistics.

    Args:
        lifetime: Lifetime aggregates containing commands, saved, and ratio.
        session: Current-session aggregates with the same fields.
        chars_per_token: Positive, validated characters-per-token estimate.

    Returns:
        The compatibility-preserving lifetime/session summary, or the initial
        ready message when no compressions have been recorded.
    """
    parts = ["[token-saver]"]
    for label, summary in (("Lifetime", lifetime), ("Session", session)):
        if summary["commands"] > 0:
            tokens = estimate_tokens(int(summary["saved"]), chars_per_token)
            parts.append(
                f"{label}: {summary['commands']} cmds, "
                f"{format_tokens(tokens)} saved ({summary['ratio']}%)"
            )
    if lifetime["commands"] == 0:
        parts.append("Ready. No compressions recorded yet.")
    return " | ".join(parts)
