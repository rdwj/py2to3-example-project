# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/itertools_helpers.py

Captures pre-migration behavior of:
- itertools.izip, imap, ifilter (removed in Py3; became builtins)
- dict.iteritems/iterkeys/viewkeys/viewitems/viewvalues
- xrange (renamed range in Py3)
- iterator .next() method (renamed __next__ in Py3)
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.itertools_helpers import (
    batch_readings, batch_with_index, sliding_window,
    group_by_key, iter_group_items, iter_group_keys,
    common_tags, changed_values, added_keys, config_values_snapshot,
    scale_readings, filter_valid_readings, zip_timestamps,
    extract_values, good_readings, paired_channels,
    take_next, peek, drain,
)


class TestBatching:
    """Characterize batch iteration."""

    def test_batch_readings(self):
        """Captures: batching iterable into fixed-size chunks."""
        result = list(batch_readings(range(7), 3))
        assert result == [[0, 1, 2], [3, 4, 5], [6]]

    def test_batch_empty(self):
        """Captures: empty iterable yields nothing."""
        assert list(batch_readings([], 3)) == []

    @pytest.mark.py2_behavior
    def test_batch_with_index(self):
        """Captures: itertools.izip for pairing index with batch."""
        result = list(batch_with_index(range(5), 2))
        assert result[0] == (0, [0, 1])
        assert result[1] == (1, [2, 3])
        assert result[2] == (2, [4])


class TestSlidingWindow:
    """Characterize sliding window over iterables."""

    @pytest.mark.py2_behavior
    def test_basic_window(self):
        """Captures: sliding window uses xrange and .next() method."""
        result = list(sliding_window(range(6), 3))
        assert result[0] == (0, 1, 2)
        assert result[1] == (1, 2, 3)
        assert result[-1] == (3, 4, 5)

    def test_window_equal_to_input(self):
        """Captures: window size == input length yields one window."""
        result = list(sliding_window([1, 2, 3], 3))
        assert len(result) == 1
        assert result[0] == (1, 2, 3)


class TestGrouping:
    """Characterize key-based grouping."""

    def test_group_by_key(self):
        """Captures: items grouped by key function into dict of lists."""
        items = [("a", 1), ("b", 2), ("a", 3)]
        result = group_by_key(items, lambda x: x[0])
        assert result["a"] == [("a", 1), ("a", 3)]
        assert result["b"] == [("b", 2)]

    @pytest.mark.py2_behavior
    def test_iter_group_items(self):
        """Captures: dict.iteritems() for lazy iteration. Removed in Py3."""
        groups = {"a": [1], "b": [2]}
        items = list(iter_group_items(groups))
        assert len(items) == 2

    @pytest.mark.py2_behavior
    def test_iter_group_keys(self):
        """Captures: dict.iterkeys() for lazy key iteration. Removed in Py3."""
        groups = {"a": [1], "b": [2]}
        keys = list(iter_group_keys(groups))
        assert set(keys) == {"a", "b"}


class TestViewOperations:
    """Characterize dict view-based set operations."""

    @pytest.mark.py2_behavior
    def test_common_tags(self):
        """Captures: dict.viewkeys() & operator. viewkeys removed in Py3."""
        a = {"TEMP": 1, "FLOW": 2, "PRESSURE": 3}
        b = {"FLOW": 10, "PRESSURE": 20, "VIBRATION": 30}
        result = common_tags(a, b)
        assert result == {"FLOW", "PRESSURE"}

    @pytest.mark.py2_behavior
    def test_added_keys(self):
        """Captures: dict.viewkeys() - operator."""
        old = {"A": 1}
        new = {"A": 1, "B": 2, "C": 3}
        result = added_keys(old, new)
        assert result == {"B", "C"}

    @pytest.mark.py2_behavior
    def test_changed_values(self):
        """Captures: dict.viewitems() ^ (symmetric difference)."""
        old = {"A": 1, "B": 2, "C": 3}
        new = {"A": 1, "B": 99, "C": 3}
        result = changed_values(old, new)
        assert "B" in result
        assert result["B"] == (2, 99)
        assert "A" not in result

    @pytest.mark.py2_behavior
    def test_config_values_snapshot(self):
        """Captures: dict.viewvalues() to list."""
        config = {"timeout": 30, "retries": 3}
        result = config_values_snapshot(config)
        assert set(result) == {30, 3}


class TestTransformations:
    """Characterize lazy transformation functions."""

    @pytest.mark.py2_behavior
    def test_scale_readings(self):
        """Captures: itertools.imap for lazy scaling."""
        result = list(scale_readings([2, 4, 6], 0.5))
        assert result == [1.0, 2.0, 3.0]

    @pytest.mark.py2_behavior
    def test_zip_timestamps(self):
        """Captures: itertools.izip for pairing channels."""
        result = list(zip_timestamps([1, 2], [3, 4]))
        assert result == [(1, 3), (2, 4)]


class TestIteratorHelpers:
    """Characterize .next() method and consumption helpers."""

    @pytest.mark.py2_behavior
    def test_take_next(self):
        """Captures: iterator.next() method. Removed in Py3; use next()."""
        it = iter([10, 20, 30])
        assert take_next(it) == 10

    @pytest.mark.py2_behavior
    def test_peek(self):
        """Captures: peek uses .next() then itertools.chain to replay."""
        it = iter([1, 2, 3])
        val, new_it = peek(it)
        assert val == 1
        assert list(new_it) == [1, 2, 3]

    def test_drain_with_limit(self):
        """Captures: drain consumes up to limit items."""
        it = iter(range(10))
        result = drain(it, limit=3)
        assert result == [0, 1, 2]

    def test_drain_all(self):
        """Captures: drain without limit consumes everything."""
        it = iter([1, 2, 3])
        result = drain(it)
        assert result == [1, 2, 3]
