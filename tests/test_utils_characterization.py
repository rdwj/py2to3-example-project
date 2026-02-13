# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/utils.py

Captures pre-migration behavior of:
- apply() builtin (removed in Py3)
- reduce() builtin (moved to functools in Py3)
- intern() builtin (moved to sys.intern in Py3)
- dict.has_key() (removed in Py3)
- backtick repr `obj` (removed in Py3)
- <> operator (removed in Py3)
- xrange() (renamed range in Py3)
- raw_input() (renamed input in Py3)
- sets.Set (deprecated, use builtin set)
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.utils import (
    call_with_args, aggregate_values, intern_tag,
    get_nested, merge_dicts, debug_repr, values_differ,
    sample_indices, chunked_range, unique_tags, build_tag_set,
    platform_summary,
)


class TestCallWithArgs:
    """Characterize apply()-based function calling."""

    @pytest.mark.py2_behavior
    def test_call_positional(self):
        """Captures: apply(func, args) for positional arguments. Removed in Py3."""
        result = call_with_args(sum, [[1, 2, 3]])
        assert result == 6

    @pytest.mark.py2_behavior
    def test_call_with_kwargs(self):
        """Captures: apply(func, args, kwargs) with keyword arguments."""
        def fn(a, b, sep="-"):
            return "%s%s%s" % (a, sep, b)
        result = call_with_args(fn, ("hello", "world"), {"sep": "+"})
        assert result == "hello+world"


class TestAggregateValues:
    """Characterize reduce() builtin usage."""

    @pytest.mark.py2_behavior
    def test_sum_with_initial(self):
        """Captures: reduce(func, seq, initial). Moved to functools in Py3."""
        result = aggregate_values(lambda a, b: a + b, [1, 2, 3], 0)
        assert result == 6

    @pytest.mark.py2_behavior
    def test_max_without_initial(self):
        """Captures: reduce without initial value."""
        result = aggregate_values(lambda a, b: a if a > b else b, [3, 1, 4, 1, 5])
        assert result == 5


class TestInternTag:
    """Characterize string interning."""

    @pytest.mark.py2_behavior
    def test_intern_returns_same_string(self):
        """Captures: intern() builtin. Moved to sys.intern() in Py3."""
        result = intern_tag("TEMP-001")
        assert result == "TEMP-001"


class TestDictHelpers:
    """Characterize dict utility functions."""

    @pytest.mark.py2_behavior
    def test_get_nested(self):
        """Captures: get_nested uses has_key(). Removed in Py3."""
        data = {"a": {"b": {"c": 42}}}
        assert get_nested(data, "a", "b", "c") == 42
        assert get_nested(data, "a", "x") is None
        assert get_nested(data, "z") is None

    @pytest.mark.py2_behavior
    def test_merge_dicts(self):
        """Captures: merge_dicts uses has_key() for __override__ check."""
        result = merge_dicts({"a": 1}, {"b": 2}, {"a": 3})
        assert result == {"a": 3, "b": 2}

    @pytest.mark.py2_behavior
    def test_merge_dicts_override(self):
        """Captures: __override__ key clears previous entries."""
        result = merge_dicts({"a": 1}, {"__override__": True, "b": 2})
        assert "a" not in result
        assert result["b"] == 2


class TestDebugRepr:
    """Characterize backtick repr operator."""

    @pytest.mark.py2_behavior
    def test_debug_repr_string(self):
        """Captures: backtick `obj` operator. Removed in Py3; use repr()."""
        result = debug_repr("hello")
        assert result == repr("hello")

    @pytest.mark.py2_behavior
    def test_debug_repr_number(self):
        """Captures: backtick on numeric values."""
        result = debug_repr(42)
        assert result == repr(42)


class TestValuesDiffer:
    """Characterize <> operator."""

    @pytest.mark.py2_behavior
    def test_differ(self):
        """Captures: <> operator. Removed in Py3; use !=."""
        assert values_differ(1, 2) is True
        assert values_differ(1, 1) is False


class TestRangeHelpers:
    """Characterize xrange-based utilities."""

    @pytest.mark.py2_behavior
    def test_sample_indices(self):
        """Captures: xrange() usage. Renamed to range() in Py3."""
        result = sample_indices(0, 10, 2)
        assert result == [0, 2, 4, 6, 8]

    def test_chunked_range(self):
        """Captures: chunked_range yields (start, end) tuples."""
        chunks = list(chunked_range(10, 3))
        assert chunks == [(0, 3), (3, 6), (6, 9), (9, 10)]


class TestUniqueTagsAndBuildTagSet:
    """Characterize sets.Set and set operations."""

    @pytest.mark.py2_behavior
    def test_unique_tags(self):
        """Captures: sets.Set for dedup. Deprecated module in Py3."""
        tags = ["A", "B", "A", "C", "B"]
        result = unique_tags(tags)
        assert result == ["A", "B", "C"]

    def test_build_tag_set(self):
        """Captures: set([...]) construction with strip."""
        result = build_tag_set(["  A  ", "B", "", "  C  "])
        assert result == {"A", "B", "C"}


class TestPlatformSummary:
    """Characterize platform info helper."""

    def test_summary_format(self):
        """Captures: platform_summary returns pipe-delimited string."""
        result = platform_summary()
        assert "Python" in result
        assert "PID" in result
        assert "|" in result
