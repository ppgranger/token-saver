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

"""Behavioral contracts for explicit engine dependencies and registration."""

import pytest

import src.engine
import src.processors.base
import src.registry
from src import config


class RecordingProcessor(src.processors.base.Processor):
    """Small externally supplied processor that records invocation context."""

    wants_exit_code = True

    def __init__(
        self, name, priority, *, result="summary", handles_failure=False
    ):
        self._name = name
        self.priority = priority
        self.result = result
        self.handles_failure = handles_failure
        self.hook_patterns = [] if name == "generic" else [name]
        self.calls = []

    @property
    def name(self):
        return self._name

    def can_handle(self, command):
        return self.name == "generic" or command == self.name

    def process(self, command, output, *, exit_code=None):
        self.calls.append((command, output, exit_code))
        return self.result


@pytest.fixture
def settings():
    return {
        "enabled": True,
        "min_input_length": 1,
        "min_compression_ratio": 0.0,
        "disabled_processors": [],
        "max_chain_depth": 3,
        "recover_critical_lines": 20,
    }


def test_explicit_dependencies_skip_discovery_and_global_configuration(
    monkeypatch, settings
):
    def unexpected(*args, **kwargs):
        pytest.fail(
            "An explicitly configured engine must not load global dependencies"
        )

    monkeypatch.setattr(
        "src.engine.processor_discovery.discover_processors", unexpected
    )
    monkeypatch.setattr(config, "get", unexpected)
    custom = RecordingProcessor("custom", 10)
    generic = RecordingProcessor("generic", 999)
    engine = src.engine.CompressionEngine([generic, custom], settings=settings)

    assert engine.compress("custom", "verbose output " * 10) == (
        "summary",
        "custom",
        True,
    )
    assert custom.calls == [("custom", "verbose output " * 10, None)]
    assert not generic.calls


def test_two_engines_can_use_independent_thresholds(settings):
    output = "verbose output " * 10
    compressing = src.engine.CompressionEngine(
        [RecordingProcessor("generic", 999)], settings=settings
    )
    passthrough = src.engine.CompressionEngine(
        [RecordingProcessor("generic", 999)],
        settings={**settings, "min_input_length": len(output) + 1},
    )

    assert compressing.compress("unknown", output) == (
        "summary",
        "generic",
        True,
    )
    assert passthrough.compress("unknown", output) == (output, "none", False)


def test_default_engine_settings_remain_live(monkeypatch, settings):
    monkeypatch.setattr(config, "_config", settings)
    engine = src.engine.CompressionEngine([RecordingProcessor("generic", 999)])
    output = "verbose output " * 10

    assert engine.compress("unknown", output)[2] is True
    monkeypatch.setattr(config, "_config", {**settings, "enabled": False})
    assert engine.compress("unknown", output) == (output, "none", False)


def test_disabled_processor_uses_named_fallback_even_if_generic_is_disabled(
    settings,
):
    custom = RecordingProcessor("custom", 10)
    generic = RecordingProcessor("generic", 999)
    engine = src.engine.CompressionEngine(
        [custom, generic],
        settings={**settings, "disabled_processors": ["custom", "generic"]},
    )

    assert engine.compress("custom", "verbose output " * 10) == (
        "summary",
        "generic",
        True,
    )
    assert not custom.calls


@pytest.mark.parametrize("handles_failure", [False, True])
def test_injected_processors_preserve_failure_routing_and_exit_code(
    settings, handles_failure
):
    custom = RecordingProcessor("custom", 10, handles_failure=handles_failure)
    generic = RecordingProcessor("generic", 999)
    engine = src.engine.CompressionEngine([custom, generic], settings=settings)
    output = "verbose output " * 10
    selected = custom if handles_failure else generic
    skipped = generic if handles_failure else custom

    assert engine.compress("custom", output, exit_code=7) == (
        "summary",
        selected.name,
        True,
    )
    assert selected.calls == [("custom", output, 7)]
    assert not skipped.calls
    assert engine.last_event["failure_fallback"] is not handles_failure


def test_registry_uses_same_active_processors_for_routing_and_hooks():
    registry = src.registry.ProcessorRegistry(
        [
            RecordingProcessor("generic", 999),
            RecordingProcessor("zebra", 10),
            RecordingProcessor("alpha", 10),
            RecordingProcessor("disabled", 1),
        ],
        disabled=["disabled", "generic"],
    )

    assert [processor.name for processor in registry.processors] == [
        "alpha",
        "zebra",
        "generic",
    ]
    assert registry.hook_patterns() == ["alpha", "zebra"]
    assert registry.generic is registry.by_name["generic"]


@pytest.mark.parametrize(
    "processors", [[], [RecordingProcessor("custom", 999)]]
)
def test_missing_named_fallback_fails_at_construction(processors, settings):
    with pytest.raises(
        ValueError, match="Exactly one processor named 'generic'"
    ):
        src.engine.CompressionEngine(processors, settings=settings)


def test_multiple_generic_fallbacks_are_rejected():
    with pytest.raises(
        ValueError, match="Exactly one processor named 'generic'"
    ):
        src.registry.ProcessorRegistry(
            [
                RecordingProcessor("generic", 999),
                RecordingProcessor("generic", 999),
            ]
        )


@pytest.mark.parametrize("priority", [999, 1000])
def test_later_processor_cannot_silently_become_generic_fallback(priority):
    with pytest.raises(
        ValueError, match="must be the lowest-priority processor"
    ):
        src.registry.ProcessorRegistry(
            [
                RecordingProcessor("generic", 999),
                RecordingProcessor("zebra", priority),
            ]
        )
