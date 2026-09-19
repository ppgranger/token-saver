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

"""Check retention redaction without losing neighboring actionable output."""

import json

import pytest

from src import delta_redaction


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("PASSWORD=synthetic-value", "PASSWORD=***"),
        ("export APP_TOKEN=synthetic-value", "export APP_TOKEN=***"),
        ("secret = 'synthetic value'", "secret = '***'"),
        ('api_key = "synthetic value"', 'api_key = "***"'),
        ('password: str = "synthetic value"', 'password: str = "***"'),
        (
            "token: bytes | None = b'synthetic-value'",
            "token: bytes | None = b'***'",
        ),
        ('password = r"synthetic value"', 'password = r"***"'),
        ('password = f"synthetic {value}"', 'password = f"***"'),
        ('{"password": "synthetic value"}', '{"password": "***"}'),
        ('{"credentials": 1234}', '{"credentials": "***"}'),
        ("{\"private_key\":'synthetic-value'}", "{\"private_key\":'***'}"),
        (
            "options={'access_key': 'synthetic-value'}",
            "options={'access_key': '***'}",
        ),
        ("service.passwd: synthetic-value", "service.passwd: ***"),
        (
            "service-secret = synthetic-value # comment",
            "service-secret = *** # comment",
        ),
        (
            "E   assert password == 'required'",
            "E   assert password == 'required'",
        ),
        (
            "E   client(token='synthetic-value', timeout=2)",
            "E   client(token='***', timeout=2)",
        ),
        ('password="unterminated synthetic value', 'password="***'),
        ("?token=synthetic-value&limit=10", "?token=***&limit=10"),
        ("TOKEN=\nValueError: retry", "TOKEN=\nValueError: retry"),
        ('token=""', 'token=""'),
    ],
)
def test_assignment_mask_keeps_surrounding_shape(original, expected):
    assert delta_redaction.sanitize(original) == expected
    assert delta_redaction.sanitize(expected) == expected


@pytest.mark.parametrize(
    "value",
    [
        'synthetic "quoted" value',
        "synthetic \\ escaped value",
        "synthetic \\" + '" quoted value',
        "échec\t秘密",
    ],
)
def test_json_escaped_value_remains_valid_json(value):
    original = json.dumps({"token": value, "error": "still broken"})

    result = delta_redaction.sanitize(original)

    assert json.loads(result) == {"token": "***", "error": "still broken"}
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize(
    "value",
    [
        'synthetic "quoted" value',
        "synthetic" + "\\" * 1,
        "synthetic" + "\\" * 2,
        "synthetic" + "\\" * 3,
        'synthetic"' + "\\" * 2 + '"',
    ],
)
def test_json_encoded_inside_string_masks_whole_escaped_value(value):
    inner = json.dumps({"token": value, "count": 2})
    original = json.dumps({"output": inner})

    result = delta_redaction.sanitize(original)

    assert json.loads(json.loads(result)["output"]) == {
        "token": "***",
        "count": 2,
    }
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize("scheme", ["Bearer", "Basic", "bearer", "BASIC"])
def test_authorization_header_preserves_scheme(scheme):
    original = f"Authorization: {scheme} synthetic-value\r\nHTTP 403\r\n"

    assert delta_redaction.sanitize(original) == (
        f"Authorization: {scheme} ***\r\nHTTP 403\r\n"
    )


@pytest.mark.parametrize(
    "original",
    [
        '{"Authorization": "Bearer synthetic-value", "status": 403}',
        "E   headers = {'authorization': 'Basic synthetic-value'}",
        "Proxy-Authorization: Bearer synthetic-value",
    ],
)
def test_quoted_and_proxy_authorization_masks_credential(original):
    result = delta_redaction.sanitize(original)

    assert "synthetic-value" not in result
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize(
    "original",
    [
        "https://user:synthetic-value@example.invalid/path",
        "postgresql://user:synthetic%40value@example.invalid:5432/db",
        "redis://default:synthetic:value@example.invalid/0",
        "redis://:synthetic-value@example.invalid/0",
        "amqp://:synthetic%40value@example.invalid/vhost",
    ],
)
def test_url_password_masks_password_without_losing_location(original):
    result = delta_redaction.sanitize(original)

    assert "synthetic" not in result
    assert "***@example.invalid" in result
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize(
    "token",
    [
        "ghp_" + "a" * 36,
        "gho_" + "b" * 36,
        "github_pat_" + "c" * 22 + "_" + "d" * 59,
        "AKIA" + "A" * 16,
        "ASIA" + "B" * 16,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c3ludGhldGlj",
    ],
)
def test_known_token_shape_masks_unlabeled_secret(token):
    original = f"E   received '{token}' instead of expected value\n"

    result = delta_redaction.sanitize(original)

    assert result == "E   received '***' instead of expected value\n"
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize("kind", ["", "RSA ", "EC ", "OPENSSH ", "ENCRYPTED "])
@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_private_key_masks_each_body_line_and_keeps_diagnostic(kind, ending):
    original = ending.join(
        [
            f"-----BEGIN {kind}PRIVATE KEY-----",
            "synthetic-body-line-1",
            "synthetic-body-line-2",
            f"-----END {kind}PRIVATE KEY-----",
            "tests/test_keys.py:14: AssertionError: key rejected",
        ]
    )

    result = delta_redaction.sanitize(original)

    assert "synthetic" not in result
    assert result.count(ending) == original.count(ending)
    assert f"{ending}***{ending}***{ending}" in result
    assert result.endswith(
        "tests/test_keys.py:14: AssertionError: key rejected"
    )
    assert delta_redaction.sanitize(result) == result


def test_unterminated_private_key_masks_remaining_body():
    original = "-----BEGIN PRIVATE KEY-----\nsynthetic-body\nremaining-body"

    assert delta_redaction.sanitize(original) == (
        "-----BEGIN PRIVATE KEY-----\n***\n***"
    )


def test_multiline_source_literal_keeps_line_breaks():
    original = 'password = """synthetic\r\nmultiline\r\nvalue"""\nassert failed'

    result = delta_redaction.sanitize(original)

    assert result == 'password = """***\r\n***\r\n***"""\nassert failed'
    assert delta_redaction.sanitize(result) == result


@pytest.mark.parametrize(
    "original",
    [
        "",
        "GIT_AUTHOR_NAME=Philippe\nMONKEY=banana\nKEYBOARD=azerty\n",
        "tests/test_tokens.py::test_refresh FAILED\r\n",
        "FAILED tests/test_tokens.py::test_refresh - TokenExpired: expired",
        "src/tokens.py:12:9: F821 Undefined name `token`\n",
        "E   assert token == expected\nE   TokenExpired: refresh required\n",
        "AssertionError: password was rejected; expected error code 403\n",
        "ValueError: échec de connexion; 秘密\r\n",
        "https://example.invalid/path?count=20",
        "PUBLIC_KEY=synthetic-public-value",
        "ghp_short_example",
    ],
)
def test_ordinary_diagnostics_and_identifiers_remain_unchanged(original):
    assert delta_redaction.sanitize(original) == original


def test_unicode_secret_masks_before_preserving_next_failure():
    original = (
        'E   password = "secret synthétique 密码"\r\n'
        "tests/test_login.py:23: AssertionError: échec\r\n"
    )

    assert delta_redaction.sanitize(original) == (
        'E   password = "***"\r\n'
        "tests/test_login.py:23: AssertionError: échec\r\n"
    )


def test_long_value_is_entirely_redacted_without_truncation():
    original = 'token="' + "synthetic" * 20000 + '"\nValueError: failed\n'

    assert delta_redaction.sanitize(original) == (
        'token="***"\nValueError: failed\n'
    )


@pytest.mark.parametrize(
    "value",
    [
        "synthetic#suffix",
        "synthetic&suffix",
        "synthetic;[]{}()suffix",
        "synthetic'quoted'suffix",
        'synthetic"quoted"suffix',
        "synthetic value with spaces",
    ],
)
@pytest.mark.parametrize(
    "prefix", ["PASSWORD=", "export API_KEY=", " token = "]
)
def test_unquoted_environment_punctuation_is_entirely_masked(prefix, value):
    original = f"{prefix}{value}\r\nAssertionError: retained\r\n"

    result = delta_redaction.sanitize(original)

    assert result == f"{prefix}***\r\nAssertionError: retained\r\n"
    assert delta_redaction.sanitize(result) == result


def test_bare_authorization_punctuation_is_entirely_masked():
    assert (
        delta_redaction.sanitize(
            "Authorization: Bearer synthetic#suffix&tail\nHTTP 403\n"
        )
        == "Authorization: Bearer ***\nHTTP 403\n"
    )


def test_url_query_mask_keeps_next_parameter_and_fragment():
    original = "https://example.invalid/?token=synthetic&limit=10#section"

    assert delta_redaction.sanitize(original) == (
        "https://example.invalid/?token=***&limit=10#section"
    )
