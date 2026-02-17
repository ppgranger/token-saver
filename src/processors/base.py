"""Abstract base class for output processors."""

from abc import ABC, abstractmethod


class Processor(ABC):
    """Base class for all output processors.

    Subclasses must set ``priority`` and ``hook_patterns`` as class-level
    attributes so the registry can auto-discover, order, and collect patterns.

    Priority conventions:
        10-19  High priority overrides (e.g. PackageListProcessor before build)
        20-29  Core processors (git, test, build, lint)
        30-49  Specialized (network, docker, kubectl, terraform, env, search, system_info)
        50-69  Content-based (file_listing, file_content)
        999    Generic fallback (must always be last)
    """

    priority: int = 50
    hook_patterns: list[str] = []

    @abstractmethod
    def can_handle(self, command: str) -> bool:
        """Return True if this processor can handle the given command."""

    @abstractmethod
    def process(self, command: str, output: str) -> str:
        """Process and compress the output. Return compressed version."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the processor name for tracking."""
