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

"""Keep redaction through critical-line recovery, chains, and fallbacks."""

from unittest import mock

import pytest

import src.engine
import src.processors.base
import src.processors.env
import src.processors.file_content
import src.processors.generic
from src import config
from src import delta


@pytest.fixture
def engine(monkeypatch):
    # Real processor settings remain isolated from the developer's profile.
    monkeypatch.setattr(
        config, "_config", {**config._DEFAULTS, "min_compression_ratio": 0.99}
    )
    return src.engine.CompressionEngine(
        [
            src.processors.env.EnvProcessor(),
            src.processors.file_content.FileContentProcessor(),
            src.processors.generic.GenericProcessor(),
        ]
    )


@pytest.mark.parametrize("command", ["env", "printenv", "set"])
@pytest.mark.parametrize(
    "secret", ["synthetic-error-secret", "synthetic-SIGKILL-secret"]
)
def test_recovery_does_not_restore_redacted_environment_secrets(
    engine, command, secret
):
    output = "\n".join([f"VAR{i}=v" for i in range(12)] + [f"API_KEY={secret}"])

    compressed, processor, changed = engine.compress(command, output)

    assert processor == "env"
    assert changed
    assert "API_KEY=***" in compressed
    assert secret not in compressed
    assert "VAR0=v" in compressed


@pytest.mark.parametrize("filename", [".env.production", ".env.local"])
def test_recovery_does_not_restore_redacted_config_secrets(engine, filename):
    output = (
        "API_KEY=synthetic-error-secret\n"
        "NORMAL_VAR=keep-me\n"
        "error: service unavailable"
    )

    compressed, processor, changed = engine.compress(f"cat {filename}", output)

    assert processor == "file_content"
    assert changed
    assert "API_KEY=***" in compressed
    assert "synthetic-error-secret" not in compressed
    assert "NORMAL_VAR=keep-me" in compressed
    assert "error: service unavailable" in compressed


@pytest.mark.parametrize("command", ["env", "printenv", "set"])
@pytest.mark.parametrize("secret", ["s", "synthetic-error-secret"])
def test_short_environment_redacts_secrets_without_losing_other_lines(
    engine, command, secret
):
    output = (
        f"API_KEY={secret}\nTERM=xterm\nPATH=/usr/bin\nerror: service "
        f"unavailable\n"
    )

    compressed, processor, changed = engine.compress(command, output)

    assert processor == "env"
    assert changed
    assert "API_KEY=***" in compressed
    assert f"API_KEY={secret}" not in compressed
    assert "TERM=xterm" in compressed
    assert "PATH=/usr/bin" in compressed
    assert "error: service unavailable" in compressed


def test_short_environment_respects_allowlist_and_line_endings(
    engine, monkeypatch
):
    monkeypatch.setitem(config._config, "redaction_allowlist", ["public_key"])
    output = (
        "PUBLIC_KEY=public-value\r\nAPI_KEY=synthetic-secret\r\nTERM=xterm\r\n"
    )

    assert src.processors.env.EnvProcessor().process("env", output) == (
        "PUBLIC_KEY=public-value\r\nAPI_KEY=***\r\nTERM=xterm\r\n"
    )


def test_short_nonsecret_environment_is_unchanged(engine):
    output = "TERM=xterm\r\nPATH=/usr/bin\r\n"

    assert engine.compress("env", output) == (output, "env", False)


@pytest.mark.parametrize("allowlisted", [False, True])
def test_long_environment_keeps_unrelated_errors_alongside_sensitive_values(
    engine, monkeypatch, allowlisted
):
    monkeypatch.setitem(
        config._config,
        "redaction_allowlist",
        ["PUBLIC_KEY"] if allowlisted else [],
    )
    output = "\n".join(
        [f"TERM_TEST_{i}=unused" for i in range(30)]
        + ["PUBLIC_KEY=synthetic-key", "error: service unavailable"]
    )

    compressed, _, _ = engine.compress("env", output)

    assert "error: service unavailable" in compressed
    if not allowlisted:
        assert "synthetic-key" not in compressed
    assert (
        src.processors.env.EnvProcessor().redacted_secrets("env", output)
        is not allowlisted
    )


class ChainStarter(src.processors.base.Processor):
    name = "chain_starter"
    priority = 10
    chain_to = ["chain_redactor"]

    def can_handle(self, command):
        return command == "chain"

    def process(self, command, output):
        return output.removeprefix("prefix:")


class ChainRedactor(src.processors.base.Processor):
    name = "chain_redactor"
    priority = 20

    def can_handle(self, command):
        return False

    def redacted_secrets(self, command, output):
        # This predicate needs the actual secondary input, after the primary
        # has removed its prefix. Checking the original input would miss it.
        return output.startswith("API_KEY=")

    def process(self, command, output):
        return (
            "API_KEY=***\n"
            "This redacted result is deliberately longer than"
            " the input."
        )


class BrokenSecondary(ChainRedactor):
    name = "broken_secondary"
    priority = 30

    def process(self, command, output):
        raise ValueError("processing failed")


class BrokenCleanup(src.processors.generic.GenericProcessor):
    def clean(self, text):
        raise ValueError("cleanup failed")


class InvalidSecondary(ChainRedactor):
    name = "invalid_secondary"
    invalid_output = None

    def process(self, command, output):
        return self.invalid_output


class InvalidCleanup(src.processors.generic.GenericProcessor):
    invalid_output = None

    def clean(self, text):
        return self.invalid_output


class UnhelpfulPrimary(ChainStarter):
    chain_to = None

    def process(self, command, output):
        return output + "\nadditional context"


class RedactingGeneric(src.processors.generic.GenericProcessor):
    def redacted_secrets(self, command, output):
        return "synthetic-error-secret" in output

    def process(self, command, output):
        return output.replace("synthetic-error-secret", "***")


class InvalidRedactingGeneric(RedactingGeneric):
    def clean(self, text):
        if "API_KEY=***" in text:
            return None
        return super().clean(text)


@pytest.mark.parametrize("failure_stage", ["chain", "cleanup"])
def test_post_redaction_failure_retains_last_safe_output(engine, failure_stage):
    primary = ChainStarter()
    redactor = ChainRedactor()
    fallback = (
        BrokenCleanup()
        if failure_stage == "cleanup"
        else src.processors.generic.GenericProcessor()
    )
    primary.chain_to = ["chain_redactor"]
    if failure_stage == "chain":
        primary.chain_to.append("broken_secondary")
    safe_engine = src.engine.CompressionEngine(
        [primary, redactor, BrokenSecondary(), fallback]
    )

    compressed, processor, changed = safe_engine.compress(
        "chain", "prefix:API_KEY=synthetic-error-secret"
    )

    assert processor == "chain_starter"
    assert changed
    assert "API_KEY=***" in compressed
    assert "synthetic-error-secret" not in compressed
    assert safe_engine.last_event["redacted"] is True


@pytest.mark.parametrize("failure_stage", ["chain", "cleanup"])
@pytest.mark.parametrize("invalid_output", [None, 0, b"private", ["private"]])
def test_invalid_extension_result_retains_prior_redaction(
    engine, failure_stage, invalid_output, caplog
):
    primary = ChainStarter()
    primary.chain_to = ["chain_redactor"]
    secondary = InvalidSecondary()
    secondary.invalid_output = invalid_output
    fallback = src.processors.generic.GenericProcessor()
    if failure_stage == "chain":
        primary.chain_to.append("invalid_secondary")
    else:
        fallback = InvalidCleanup()
        fallback.invalid_output = invalid_output
    safe_engine = src.engine.CompressionEngine(
        [primary, ChainRedactor(), secondary, fallback]
    )

    compressed, _, changed = safe_engine.compress(
        "chain", "prefix:API_KEY=synthetic-error-secret"
    )

    assert changed
    assert "API_KEY=***" in compressed
    assert "synthetic-error-secret" not in compressed
    assert safe_engine.last_event["redacted"] is True
    assert "private" not in caplog.text
    assert "synthetic-error-secret" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("route", ["direct", "mismatch"])
@pytest.mark.parametrize("invalid_cleanup", [False, True])
def test_generic_redaction_survives_cleanup_recovery_and_ratio_gates(
    engine, route, invalid_cleanup
):
    generic_processor = (
        InvalidRedactingGeneric() if invalid_cleanup else RedactingGeneric()
    )
    processors = [generic_processor]
    if route == "mismatch":
        processors.insert(0, UnhelpfulPrimary())
    safe_engine = src.engine.CompressionEngine(processors)

    compressed, processor, changed = safe_engine.compress(
        "chain", "API_KEY=synthetic-error-secret\nerror: service unavailable"
    )

    assert changed
    assert processor == "generic"
    assert "API_KEY=***" in compressed
    assert "synthetic-error-secret" not in compressed
    assert "error: service unavailable" in compressed
    assert safe_engine.last_event["redacted"] is True


def test_invalid_primary_result_is_rejected_at_extension_boundary(engine):
    primary = InvalidSecondary()
    primary.can_handle = lambda command: True
    unsafe_engine = src.engine.CompressionEngine(
        [primary, src.processors.generic.GenericProcessor()]
    )
    with pytest.raises(TypeError, match="Processor output must be text"):
        unsafe_engine.compress("chain", "ordinary output")


def test_delta_does_not_reparse_raw_input_after_generic_fallback_redaction(
    engine, monkeypatch
):
    monkeypatch.setitem(config._config, "delta_enabled", True)
    safe_engine = src.engine.CompressionEngine(
        [UnhelpfulPrimary(), RedactingGeneric()]
    )
    raw = "API_KEY=synthetic-error-secret\nerror: service unavailable"
    safe_engine.compress("chain", raw)
    with mock.patch.object(safe_engine, "diagnostics") as parse:
        actual = delta.apply(
            "chain",
            raw,
            mock.sentinel.safe_fallback,
            engine=safe_engine,
            exit_code=0,
            session_id="test-session",
        )
    assert actual is mock.sentinel.safe_fallback
    parse.assert_not_called()


def test_chain_failure_before_successful_redaction_still_raises(engine):
    primary = ChainStarter()
    primary.chain_to = ["broken_secondary"]
    unsafe_engine = src.engine.CompressionEngine(
        [primary, BrokenSecondary(), src.processors.generic.GenericProcessor()]
    )

    with pytest.raises(ValueError, match="processing failed"):
        unsafe_engine.compress("chain", "prefix:API_KEY=synthetic-secret")


def test_cleanup_failure_before_redaction_still_raises(engine):
    primary = ChainStarter()
    primary.chain_to = None
    unsafe_engine = src.engine.CompressionEngine([primary, BrokenCleanup()])

    with pytest.raises(ValueError, match="cleanup failed"):
        unsafe_engine.compress("chain", "prefix:ordinary content")


def test_secondary_redaction_survives_recovery_and_ratio_fallbacks(engine):
    chained_engine = src.engine.CompressionEngine(
        [
            ChainStarter(),
            ChainRedactor(),
            src.processors.generic.GenericProcessor(),
        ]
    )
    output = "prefix:API_KEY=synthetic-error-secret"

    compressed, processor, changed = chained_engine.compress("chain", output)

    assert processor == "chain_starter"
    assert changed
    assert len(compressed) > len(output)
    assert "API_KEY=***" in compressed
    assert "synthetic-error-secret" not in compressed
    assert chained_engine.last_event["is_mismatch"] is False


def test_unredacted_critical_lines_still_recovered(engine, monkeypatch):
    monkeypatch.setitem(config._config, "min_compression_ratio", 0.0)
    output = "\n".join(
        [f"TERM_TEST_{i}=unused" for i in range(30)]
        + ["error: service unavailable"]
    )

    compressed, processor, changed = engine.compress("env", output)

    assert processor == "env"
    assert changed
    assert "error: service unavailable" in compressed
