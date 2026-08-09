"""Tests for src/shell_syntax.py's quote-aware scanner and its consumers.

Regression coverage for GitHub issue #49: an unquoted, backslash-escaped
quote character (``\\"`` or ``\\'``) was misread by ``iter_unquoted`` as the
*start* of a quoted region — POSIX shells treat it as an ordinary literal
character instead — so the scanner swallowed the rest of the command string,
blinding every safety check built on top of it (newline/background-operator
smuggling, output redirection, dangerous constructs, chain splitting).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.shell_syntax import (
    has_output_redirection,
    has_unquoted,
    has_unquoted_background_operator,
    has_unquoted_newline,
    iter_unquoted,
)


def _visible(command: str) -> str:
    """Concatenate every character iter_unquoted considers unquoted."""
    return "".join(ch for _, ch in iter_unquoted(command))


class TestIterUnquotedEscapes:
    def test_escaped_double_quote_outside_quotes_is_not_an_opener(self):
        # `\"` outside any quoted region is a literal quote character in
        # POSIX, not the start of a double-quoted region.  The escaping
        # backslash and the escaped `"` are consumed as a literal pair and
        # not yielded (neither should be interpreted as a shell operator),
        # but everything *after* the pair must still be visible — proving
        # the scanner did not treat it as an unterminated quote opener.
        s = 'echo a \\" b && sudo id'
        assert _visible(s) == "echo a  b && sudo id"

    def test_escaped_single_quote_outside_quotes_is_not_an_opener(self):
        s = "echo a \\' b && sudo id"
        assert _visible(s) == "echo a  b && sudo id"

    def test_escaped_quote_does_not_swallow_following_newline(self):
        s = 'git status \\"\nsudo rm -rf /tmp/important'
        assert _visible(s) == "git status \nsudo rm -rf /tmp/important"

    def test_escaped_quote_does_not_swallow_following_ampersand(self):
        s = 'git status \\" & touch /tmp/probe'
        assert _visible(s) == "git status  & touch /tmp/probe"

    def test_real_double_quote_region_with_internal_escape_unchanged(self):
        # Non-regression: `"a\"b"` is still a single quoted region — the
        # escape *inside* double quotes is handled by the existing branch,
        # untouched by this fix.
        s = 'echo "a\\"b" && git status'
        assert _visible(s) == "echo  && git status"

    def test_real_single_quote_region_unchanged(self):
        # Single quotes don't support escapes at all in POSIX — 'a\' ends
        # at its second quote, with the backslash treated as a literal
        # inside the region (not consumed specially).
        s = "echo 'a\\' && git status"
        assert _visible(s) == "echo  && git status"

    def test_plain_backslash_space_is_still_consumed_as_a_pair(self):
        # A backslash escaping an ordinary character (not a quote) is also
        # consumed as a literal pair outside quotes, matching POSIX — the
        # escaped space must not be mistaken for a word boundary.
        s = "echo a\\ b && git status"
        assert _visible(s) == "echo ab && git status"

    def test_trailing_backslash_at_end_of_string_is_not_out_of_bounds(self):
        # A lone trailing backslash has no following character to escape;
        # iter_unquoted must not index past the end of the string.
        s = "echo a\\"
        assert _visible(s) == s


class TestNewlineSmugglingClosed:
    def test_bare_newline_still_rejected(self):
        assert has_unquoted_newline("git status\nsudo rm -rf /tmp/x") is True

    def test_escaped_quote_prefix_no_longer_bypasses_newline_check(self):
        assert has_unquoted_newline('git status \\"\nsudo rm -rf /tmp/important') is True

    def test_escaped_quote_prefix_with_grep_style_payload(self):
        assert has_unquoted_newline('git log --grep=\\"fix\nsudo rm -rf /tmp/x') is True

    def test_line_continuation_still_not_flagged(self):
        # A backslash directly before the newline is a genuine POSIX line
        # continuation, not a statement separator.
        assert has_unquoted_newline("echo a \\\n&& git status") is False


class TestBackgroundOperatorSmugglingClosed:
    def test_bare_ampersand_still_rejected(self):
        assert has_unquoted_background_operator("git status & touch /tmp/probe") is True

    def test_escaped_quote_prefix_no_longer_bypasses_background_check(self):
        assert has_unquoted_background_operator('git status \\" & touch /tmp/probe') is True

    def test_double_ampersand_still_not_flagged(self):
        assert has_unquoted_background_operator("git status && echo done") is False


class TestOutputRedirectionAndDangerousConstructs:
    def test_escaped_quote_prefix_no_longer_bypasses_redirection_check(self):
        assert has_output_redirection('git status \\" > /etc/passwd') is True

    def test_escaped_quote_prefix_no_longer_bypasses_construct_check(self):
        assert has_unquoted('git status \\" $(id)', ("$(", "`", "<<")) is True
