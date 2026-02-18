# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/utils.py

Captures current Python 2 behavior for utility functions.
Critical Py2→3 issues: apply(), reduce(), intern(), has_key(), backtick repr,
<> operator, xrange, raw_input, sets module.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
from unittest.mock import patch, MagicMock

from src.core.utils import (
    call_with_args,
    aggregate_values,
    intern_tag,
    get_nested,
    merge_dicts,
    debug_repr,
    values_differ,
    sample_indices,
    chunked_range,
    prompt_user,
    confirm_action,
    unique_tags,
    build_tag_set,
    platform_summary,
)


# ============================================================================
# Function-calling helpers
# ============================================================================


class TestCallWithArgs:
    """Characterize apply() usage."""

    def test_call_with_positional_args_only(self):
        """call_with_args() invokes function with positional args."""
        def add(a, b, c):
            return a + b + c

        result = call_with_args(add, (10, 20, 30))
        assert result == 60

    def test_call_with_args_and_kwargs(self):
        """call_with_args() invokes function with args and kwargs."""
        def greet(name, greeting="Hello"):
            return "%s, %s" % (greeting, name)

        result = call_with_args(greet, ("Alice",), {"greeting": "Hi"})
        assert result == "Hi, Alice"

    def test_call_with_args_empty_args(self):
        """call_with_args() works with empty args tuple."""
        def no_args():
            return "called"

        result = call_with_args(no_args, ())
        assert result == "called"

    def test_call_with_args_none_kwargs(self):
        """call_with_args() handles None kwargs."""
        def func(x):
            return x * 2

        result = call_with_args(func, (5,), None)
        assert result == 10


class TestAggregateValues:
    """Characterize reduce() usage."""

    def test_aggregate_sum(self):
        """aggregate_values() sums sequence."""
        result = aggregate_values(lambda a, b: a + b, [1, 2, 3, 4])
        assert result == 10

    def test_aggregate_with_initial(self):
        """aggregate_values() uses initial value."""
        result = aggregate_values(lambda a, b: a + b, [1, 2, 3], initial=10)
        assert result == 16

    def test_aggregate_product(self):
        """aggregate_values() computes product."""
        result = aggregate_values(lambda a, b: a * b, [2, 3, 4], initial=1)
        assert result == 24

    def test_aggregate_max(self):
        """aggregate_values() finds maximum."""
        result = aggregate_values(max, [3, 7, 2, 9, 1])
        assert result == 9

    def test_aggregate_string_concat(self):
        """aggregate_values() concatenates strings."""
        result = aggregate_values(lambda a, b: a + " " + b, ["one", "two", "three"])
        assert result == "one two three"


# ============================================================================
# String interning
# ============================================================================


class TestInternTag:
    """Characterize intern() usage."""

    def test_intern_returns_interned_string(self):
        """intern_tag() interns the string."""
        tag1 = intern_tag("sensor.temp")
        tag2 = intern_tag("sensor.temp")
        # In Py2, intern() returns the same object
        assert tag1 is tag2

    def test_intern_different_tags(self):
        """intern_tag() interns different strings separately."""
        tag1 = intern_tag("sensor.temp")
        tag2 = intern_tag("sensor.pressure")
        assert tag1 is not tag2

    def test_intern_stores_in_cache(self):
        """intern_tag() maintains internal cache."""
        from src.core.utils import _interned_tags
        tag = intern_tag("test.tag")
        assert "test.tag" in _interned_tags


# ============================================================================
# Dictionary helpers
# ============================================================================


class TestGetNested:
    """Characterize has_key() usage."""

    def test_get_nested_single_level(self):
        """get_nested() retrieves single-level key."""
        data = {"a": 10}
        result = get_nested(data, "a")
        assert result == 10

    def test_get_nested_multi_level(self):
        """get_nested() traverses nested dicts."""
        data = {"a": {"b": {"c": 42}}}
        result = get_nested(data, "a", "b", "c")
        assert result == 42

    def test_get_nested_missing_key_returns_none(self):
        """get_nested() returns None for missing key."""
        data = {"a": {"b": 10}}
        result = get_nested(data, "a", "x")
        assert result is None

    def test_get_nested_missing_intermediate_returns_none(self):
        """get_nested() returns None if intermediate key missing."""
        data = {"a": 10}
        result = get_nested(data, "a", "b")
        assert result is None

    def test_get_nested_non_dict_returns_none(self):
        """get_nested() returns None if value is not dict."""
        data = {"a": "string"}
        result = get_nested(data, "a", "b")
        assert result is None


class TestMergeDicts:
    """Characterize dict.has_key() in merge."""

    def test_merge_two_dicts(self):
        """merge_dicts() merges dicts left-to-right."""
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 3, "c": 4}
        result = merge_dicts(d1, d2)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_override_clears(self):
        """merge_dicts() clears on __override__ key."""
        d1 = {"a": 1, "b": 2}
        d2 = {"__override__": True, "c": 3}
        result = merge_dicts(d1, d2)
        assert result == {"c": 3}
        assert "a" not in result

    def test_merge_empty_dicts(self):
        """merge_dicts() handles empty dicts."""
        result = merge_dicts({}, {})
        assert result == {}

    def test_merge_multiple_dicts(self):
        """merge_dicts() merges multiple dicts."""
        result = merge_dicts({"a": 1}, {"b": 2}, {"c": 3})
        assert result == {"a": 1, "b": 2, "c": 3}


# ============================================================================
# Comparison / diagnostic helpers
# ============================================================================


class TestDebugRepr:
    """Characterize backtick repr operator."""

    def test_debug_repr_string(self):
        """debug_repr() uses backtick for string."""
        result = debug_repr("hello")
        assert result == "'hello'"

    def test_debug_repr_number(self):
        """debug_repr() uses backtick for number."""
        result = debug_repr(42)
        assert result == "42"

    def test_debug_repr_list(self):
        """debug_repr() uses backtick for list."""
        result = debug_repr([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_debug_repr_dict(self):
        """debug_repr() uses backtick for dict."""
        result = debug_repr({"a": 1})
        # Dict repr can vary, just check it's a valid repr
        assert "a" in result

    def test_debug_repr_none(self):
        """debug_repr() uses backtick for None."""
        result = debug_repr(None)
        assert result == "None"


class TestValuesDiffer:
    """Characterize <> operator."""

    def test_values_differ_equal(self):
        """values_differ() returns False for equal values."""
        assert values_differ(10, 10) is False

    def test_values_differ_not_equal(self):
        """values_differ() returns True for different values."""
        assert values_differ(10, 20) is True

    def test_values_differ_strings(self):
        """values_differ() compares strings."""
        assert values_differ("abc", "abc") is False
        assert values_differ("abc", "xyz") is True

    def test_values_differ_types(self):
        """values_differ() compares different types."""
        assert values_differ(10, "10") is True

    def test_values_differ_none(self):
        """values_differ() handles None."""
        assert values_differ(None, None) is False
        assert values_differ(None, 0) is True


# ============================================================================
# Range / iteration
# ============================================================================


class TestSampleIndices:
    """Characterize xrange() usage."""

    def test_sample_indices_simple_range(self):
        """sample_indices() returns list of indices."""
        result = sample_indices(0, 5)
        assert result == [0, 1, 2, 3, 4]

    def test_sample_indices_with_step(self):
        """sample_indices() uses step parameter."""
        result = sample_indices(0, 10, step=2)
        assert result == [0, 2, 4, 6, 8]

    def test_sample_indices_large_range(self):
        """sample_indices() handles large ranges (uses xrange)."""
        result = sample_indices(0, 1000, step=100)
        assert result == [0, 100, 200, 300, 400, 500, 600, 700, 800, 900]

    def test_sample_indices_empty(self):
        """sample_indices() returns empty for start >= stop."""
        result = sample_indices(5, 5)
        assert result == []


class TestChunkedRange:
    """Characterize xrange in generator."""

    def test_chunked_range_even_chunks(self):
        """chunked_range() yields even chunks."""
        result = list(chunked_range(10, 3))
        assert result == [(0, 3), (3, 6), (6, 9), (9, 10)]

    def test_chunked_range_single_chunk(self):
        """chunked_range() yields single chunk if total < chunk_size."""
        result = list(chunked_range(5, 10))
        assert result == [(0, 5)]

    def test_chunked_range_exact_fit(self):
        """chunked_range() handles exact multiple."""
        result = list(chunked_range(12, 4))
        assert result == [(0, 4), (4, 8), (8, 12)]

    def test_chunked_range_uses_xrange(self):
        """chunked_range() uses xrange for large totals."""
        result = list(chunked_range(10000, 1000))
        assert len(result) == 10
        assert result[0] == (0, 1000)
        assert result[-1] == (9000, 10000)


# ============================================================================
# User interaction
# ============================================================================


class TestPromptUser:
    """Characterize raw_input() usage."""

    @patch("src.core.utils.input")
    def test_prompt_user_basic(self, mock_input):
        """prompt_user() calls raw_input."""
        mock_input.return_value = "test response"
        result = prompt_user("Enter value")
        assert result == "test response"
        mock_input.assert_called_once_with("Enter value")

    @patch("src.core.utils.input")
    def test_prompt_user_with_default(self, mock_input):
        """prompt_user() shows default in prompt."""
        mock_input.return_value = ""
        result = prompt_user("Enter value", default="default_val")
        assert result == "default_val"
        # Check prompt includes default
        call_args = mock_input.call_args[0][0]
        assert "default_val" in call_args

    @patch("src.core.utils.input")
    def test_prompt_user_overrides_default(self, mock_input):
        """prompt_user() uses user input over default."""
        mock_input.return_value = "user input"
        result = prompt_user("Enter value", default="default_val")
        assert result == "user input"

    @patch("src.core.utils.input")
    def test_prompt_user_empty_no_default(self, mock_input):
        """prompt_user() returns empty string if no default."""
        mock_input.return_value = ""
        result = prompt_user("Enter value")
        assert result == ""


class TestConfirmAction:
    """Characterize raw_input() for yes/no."""

    @patch("src.core.utils.input")
    def test_confirm_action_yes(self, mock_input):
        """confirm_action() returns True for 'y'."""
        mock_input.return_value = "y"
        assert confirm_action("Proceed?") is True

    @patch("src.core.utils.input")
    def test_confirm_action_yes_full(self, mock_input):
        """confirm_action() returns True for 'yes'."""
        mock_input.return_value = "yes"
        assert confirm_action("Proceed?") is True

    @patch("src.core.utils.input")
    def test_confirm_action_no(self, mock_input):
        """confirm_action() returns False for 'n'."""
        mock_input.return_value = "n"
        assert confirm_action("Proceed?") is False

    @patch("src.core.utils.input")
    def test_confirm_action_uppercase(self, mock_input):
        """confirm_action() handles uppercase input."""
        mock_input.return_value = "Y"
        assert confirm_action("Proceed?") is True

    @patch("src.core.utils.input")
    def test_confirm_action_whitespace(self, mock_input):
        """confirm_action() strips whitespace."""
        mock_input.return_value = "  yes  "
        assert confirm_action("Proceed?") is True


# ============================================================================
# Unique-value tracking
# ============================================================================


class TestUniqueTags:
    """Characterize sets.Set usage."""

    def test_unique_tags_removes_duplicates(self):
        """unique_tags() removes duplicates."""
        result = unique_tags(["a", "b", "a", "c", "b"])
        assert result == ["a", "b", "c"]

    def test_unique_tags_preserves_order(self):
        """unique_tags() preserves first-seen order."""
        result = unique_tags(["z", "a", "m", "a", "z"])
        assert result == ["z", "a", "m"]

    def test_unique_tags_empty(self):
        """unique_tags() handles empty input."""
        result = unique_tags([])
        assert result == []

    def test_unique_tags_no_duplicates(self):
        """unique_tags() returns all when no duplicates."""
        result = unique_tags(["a", "b", "c"])
        assert result == ["a", "b", "c"]


class TestBuildTagSet:
    """Characterize set() constructor with list."""

    def test_build_tag_set_basic(self):
        """build_tag_set() creates set from list."""
        result = build_tag_set(["a", "b", "c"])
        assert result == {"a", "b", "c"}

    def test_build_tag_set_strips_whitespace(self):
        """build_tag_set() strips whitespace from tags."""
        result = build_tag_set(["  a  ", "b", "  c  "])
        assert result == {"a", "b", "c"}

    def test_build_tag_set_filters_empty(self):
        """build_tag_set() filters out empty strings."""
        result = build_tag_set(["a", "", "  ", "b"])
        assert result == {"a", "b"}

    def test_build_tag_set_empty_input(self):
        """build_tag_set() returns empty set for empty input."""
        result = build_tag_set([])
        assert result == set()


# ============================================================================
# Platform info
# ============================================================================


class TestPlatformSummary:
    """Characterize platform info string."""

    def test_platform_summary_includes_python_version(self):
        """platform_summary() includes Python version."""
        result = platform_summary()
        assert "Python" in result

    def test_platform_summary_includes_pid(self):
        """platform_summary() includes process ID."""
        result = platform_summary()
        assert "PID" in result

    def test_platform_summary_includes_platform(self):
        """platform_summary() includes platform name."""
        result = platform_summary()
        assert "Platform" in result

    def test_platform_summary_format(self):
        """platform_summary() uses pipe separator."""
        result = platform_summary()
        assert "|" in result
