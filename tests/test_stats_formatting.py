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

"""Keep statistics rendering independent of profiles and SQLite access."""

import pytest

from src import stats_formatting


@pytest.mark.parametrize(
    ("characters", "ratio", "expected"),
    [(0, 4, 0), (-100, 4, 0), (1, 4, 1), (400, 4, 100), (400, 8, 50)],
)
def test_token_estimate_uses_explicit_conversion(characters, ratio, expected):
    assert stats_formatting.estimate_tokens(characters, ratio) == expected


def test_empty_message_retains_historical_text():
    empty = {"commands": 0, "saved": 0, "ratio": 0.0}
    assert (
        stats_formatting.format_stats_message(empty, empty, chars_per_token=4)
        == "[token-saver] | Ready. No compressions recorded yet."
    )


def test_message_renders_lifetime_and_session_with_explicit_conversion():
    lifetime = {"commands": 12, "saved": 8000, "ratio": 80.0}
    session = {"commands": 2, "saved": 400, "ratio": 40.0}
    assert stats_formatting.format_stats_message(
        lifetime, session, chars_per_token=4
    ) == (
        "[token-saver] | Lifetime: 12 cmds, 2.0k tokens saved (80.0%)"
        " | Session: 2 cmds, 100 tokens saved (40.0%)"
    )
    assert stats_formatting.format_stats_message(
        lifetime, session, chars_per_token=8
    ) == (
        "[token-saver] | Lifetime: 12 cmds, 1.0k tokens saved (80.0%)"
        " | Session: 2 cmds, 50 tokens saved (40.0%)"
    )


def test_message_omits_empty_current_session():
    lifetime = {"commands": 1, "saved": 8000000, "ratio": 50.0}
    empty = {"commands": 0, "saved": 0, "ratio": 0.0}
    assert (
        stats_formatting.format_stats_message(
            lifetime, empty, chars_per_token=4
        )
        == "[token-saver] | Lifetime: 1 cmds, 2.0M tokens saved (50.0%)"
    )
