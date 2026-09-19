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

"""Processor registration rules, independent of discovery and compression."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.processors import base


class ProcessorRegistry:
    """Build the ordered routing table and its named fallback.

    Discovery supplies instances; the registry does not import plugins or read
    configuration. Keeping those concerns separate also lets callers build an
    engine with an explicit set of processors, without loading user plugins.

    Attributes:
        processors: Enabled processor instances in routing priority order.
        generic: Required generic fallback, always last in the routing order.
        by_name: Enabled instances indexed by their declared names.
    """

    def __init__(
        self,
        processors: Iterable[base.Processor],
        *,
        disabled: Iterable[str] = (),
    ) -> None:
        """Validate and order an explicit collection of processors.

        Args:
            processors: Instances available for routing and processor chaining.
            disabled: Names excluded from routing, except the generic fallback.

        Raises:
            ValueError: There is not exactly one generic fallback at priority
                999, or another processor sorts after it.
        """
        disabled_names = set(disabled) - {"generic"}
        self.processors = sorted(
            (
                processor
                for processor in processors
                if processor.name not in disabled_names
            ),
            key=lambda processor: (processor.priority, processor.name),
        )
        fallbacks = [
            processor
            for processor in self.processors
            if processor.name == "generic"
        ]
        if len(fallbacks) != 1:
            raise ValueError(
                "Exactly one processor named 'generic' is required"
            )
        self.generic = fallbacks[0]
        if (
            self.generic.priority != 999
            or self.processors[-1] is not self.generic
        ):
            raise ValueError(
                "GenericProcessor (priority 999) must be the "
                "lowest-priority processor"
            )
        self.by_name = {
            processor.name: processor for processor in self.processors
        }

    def hook_patterns(self) -> list[str]:
        """Return interception patterns in active processor routing order."""
        patterns = []
        for processor in self.processors:
            patterns.extend(processor.hook_patterns)
        return patterns
