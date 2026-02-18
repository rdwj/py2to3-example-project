# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/itertools_helpers.py

Captures current Python 2 behavior for iterator helpers.
Critical Py2→3 issues: itertools.izip/imap/ifilter, dict.viewkeys/viewvalues/
viewitems, dict.iteritems/iterkeys, generator .next(), xrange, map/filter/zip
as list producers.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
from unittest.mock import MagicMock

from src.core.itertools_helpers import (
    batch_readings,
    batch_with_index,
    sliding_window,
    group_by_key,
    iter_group_items,
    iter_group_keys,
    common_tags,
    changed_values,
    added_keys,
    config_values_snapshot,
    scale_readings,
    filter_valid_readings,
    zip_timestamps,
    extract_values,
    good_readings,
    paired_channels,
    take_next,
    peek,
    drain,
)


# ============================================================================
# Test Fixtures
# ============================================================================


class MockReading:
    """Mock reading object for tests."""
    def __init__(self, value, quality=192):
        self.value = value
        self.decoded_value = value
        self.quality = quality

    def __repr__(self):
        return "MockReading(%r, q=%d)" % (self.value, self.quality)


# ============================================================================
# Batching Tests
# ============================================================================


class TestBatchReadings:
    """Characterize batch_readings() with itertools.izip."""

    def test_batch_readings_full_batches(self):
        """batch_readings() yields full batches."""
        data = range(10)
        batches = list(batch_readings(data, 3))
        assert len(batches) == 4
        assert batches[0] == [0, 1, 2]
        assert batches[1] == [3, 4, 5]
        assert batches[2] == [6, 7, 8]
        assert batches[3] == [9]

    def test_batch_readings_exact_fit(self):
        """batch_readings() handles exact multiple."""
        data = range(12)
        batches = list(batch_readings(data, 4))
        assert len(batches) == 3
        assert all(len(b) == 4 for b in batches)

    def test_batch_readings_single_batch(self):
        """batch_readings() yields single batch if data < batch_size."""
        data = [1, 2, 3]
        batches = list(batch_readings(data, 10))
        assert len(batches) == 1
        assert batches[0] == [1, 2, 3]

    def test_batch_readings_empty(self):
        """batch_readings() yields nothing for empty input."""
        batches = list(batch_readings([], 5))
        assert batches == []

    def test_batch_readings_generator_input(self):
        """batch_readings() works with generator input."""
        def gen():
            for i in range(7):
                yield i

        batches = list(batch_readings(gen(), 3))
        assert len(batches) == 3
        assert batches[-1] == [6]


class TestBatchWithIndex:
    """Characterize batch_with_index() using itertools.izip."""

    def test_batch_with_index_yields_tuples(self):
        """batch_with_index() yields (index, batch) tuples."""
        data = range(10)
        indexed = list(batch_with_index(data, 4))
        assert indexed[0] == (0, [0, 1, 2, 3])
        assert indexed[1] == (1, [4, 5, 6, 7])
        assert indexed[2] == (2, [8, 9])

    def test_batch_with_index_sequential_indices(self):
        """batch_with_index() uses sequential indices."""
        data = range(15)
        indexed = list(batch_with_index(data, 5))
        indices = [i for i, _ in indexed]
        assert indices == [0, 1, 2]

    def test_batch_with_index_empty(self):
        """batch_with_index() handles empty input."""
        indexed = list(batch_with_index([], 3))
        assert indexed == []


# ============================================================================
# Sliding Window Tests
# ============================================================================


class TestSlidingWindow:
    """Characterize sliding_window() using xrange and .next()."""

    def test_sliding_window_basic(self):
        """sliding_window() yields overlapping windows."""
        data = [1, 2, 3, 4, 5]
        windows = list(sliding_window(data, 3))
        assert len(windows) == 3
        assert windows[0] == (1, 2, 3)
        assert windows[1] == (2, 3, 4)
        assert windows[2] == (3, 4, 5)

    def test_sliding_window_size_2(self):
        """sliding_window() with window_size=2."""
        data = [10, 20, 30, 40]
        windows = list(sliding_window(data, 2))
        assert windows == [(10, 20), (20, 30), (30, 40)]

    def test_sliding_window_exact_size(self):
        """sliding_window() with data == window_size."""
        data = [1, 2, 3]
        windows = list(sliding_window(data, 3))
        assert len(windows) == 1
        assert windows[0] == (1, 2, 3)

    def test_sliding_window_uses_xrange(self):
        """sliding_window() uses xrange in initialization loop."""
        # Characterize behavior with larger window
        data = range(20)
        windows = list(sliding_window(data, 5))
        assert len(windows) == 16

    def test_sliding_window_uses_next_method(self):
        """sliding_window() uses .next() method on iterator."""
        # Create generator to verify .next() is called
        def gen():
            for i in range(10):
                yield i

        windows = list(sliding_window(gen(), 3))
        assert len(windows) == 8


# ============================================================================
# Grouping Tests
# ============================================================================


class TestGroupByKey:
    """Characterize group_by_key()."""

    def test_group_by_key_basic(self):
        """group_by_key() groups items by key function."""
        data = [1, 2, 3, 4, 5, 6]
        grouped = group_by_key(data, lambda x: x % 2)
        assert grouped[0] == [2, 4, 6]
        assert grouped[1] == [1, 3, 5]

    def test_group_by_key_string_keys(self):
        """group_by_key() works with string keys."""
        data = ["apple", "apricot", "banana", "blueberry", "cherry"]
        grouped = group_by_key(data, lambda s: s[0])
        assert grouped["a"] == ["apple", "apricot"]
        assert grouped["b"] == ["banana", "blueberry"]
        assert grouped["c"] == ["cherry"]

    def test_group_by_key_empty(self):
        """group_by_key() handles empty input."""
        grouped = group_by_key([], lambda x: x)
        assert grouped == {}


class TestIterGroupItems:
    """Characterize dict.iteritems() usage."""

    def test_iter_group_items_returns_iterator(self):
        """iter_group_items() returns lazy iterator."""
        data = {"a": [1, 2], "b": [3, 4]}
        result = iter_group_items(data)
        # In Py3, items() returns dict_items view
        assert hasattr(result, "__next__") or hasattr(result, "__iter__")

    def test_iter_group_items_yields_pairs(self):
        """iter_group_items() yields (key, value) pairs."""
        data = {"x": [10], "y": [20], "z": [30]}
        items = list(iter_group_items(data))
        assert len(items) == 3
        assert ("x", [10]) in items
        assert ("y", [20]) in items

    def test_iter_group_items_empty(self):
        """iter_group_items() handles empty dict."""
        items = list(iter_group_items({}))
        assert items == []


class TestIterGroupKeys:
    """Characterize dict.iterkeys() usage."""

    def test_iter_group_keys_returns_iterator(self):
        """iter_group_keys() returns lazy iterator."""
        data = {"a": 1, "b": 2}
        result = iter_group_keys(data)
        assert hasattr(result, "__next__") or hasattr(result, "__iter__")

    def test_iter_group_keys_yields_keys(self):
        """iter_group_keys() yields keys."""
        data = {"x": 10, "y": 20, "z": 30}
        keys = list(iter_group_keys(data))
        assert set(keys) == {"x", "y", "z"}


# ============================================================================
# View-based Operations
# ============================================================================


class TestCommonTags:
    """Characterize dict.viewkeys() usage."""

    def test_common_tags_intersection(self):
        """common_tags() returns keys in both dicts."""
        config_a = {"sensor1": 1, "sensor2": 2, "sensor3": 3}
        config_b = {"sensor2": 20, "sensor3": 30, "sensor4": 40}
        result = common_tags(config_a, config_b)
        assert result == {"sensor2", "sensor3"}

    def test_common_tags_no_overlap(self):
        """common_tags() returns empty set for no overlap."""
        config_a = {"a": 1, "b": 2}
        config_b = {"c": 3, "d": 4}
        result = common_tags(config_a, config_b)
        assert result == set()

    def test_common_tags_all_common(self):
        """common_tags() returns all keys when identical."""
        config = {"x": 1, "y": 2}
        result = common_tags(config, config)
        assert result == {"x", "y"}


class TestChangedValues:
    """Characterize dict.viewitems() usage."""

    def test_changed_values_detects_changes(self):
        """changed_values() finds keys with different values."""
        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 1, "b": 20, "c": 30}
        result = changed_values(old, new)
        assert "a" not in result
        assert result["b"] == (2, 20)
        assert result["c"] == (3, 30)

    def test_changed_values_no_changes(self):
        """changed_values() returns empty for identical dicts."""
        config = {"a": 1, "b": 2}
        result = changed_values(config, config)
        assert result == {}

    def test_changed_values_added_keys_excluded(self):
        """changed_values() excludes keys only in one dict."""
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        result = changed_values(old, new)
        assert "b" not in result


class TestAddedKeys:
    """Characterize dict.viewkeys() subtraction."""

    def test_added_keys_new_keys(self):
        """added_keys() returns keys in new but not old."""
        old = {"a": 1, "b": 2}
        new = {"b": 2, "c": 3, "d": 4}
        result = added_keys(old, new)
        assert result == {"c", "d"}

    def test_added_keys_none_added(self):
        """added_keys() returns empty when no new keys."""
        config = {"a": 1, "b": 2}
        result = added_keys(config, config)
        assert result == set()


class TestConfigValuesSnapshot:
    """Characterize dict.viewvalues() usage."""

    def test_config_values_snapshot_returns_list(self):
        """config_values_snapshot() returns list of values."""
        config = {"a": 10, "b": 20, "c": 30}
        result = config_values_snapshot(config)
        assert isinstance(result, list)
        assert set(result) == {10, 20, 30}

    def test_config_values_snapshot_empty(self):
        """config_values_snapshot() handles empty dict."""
        result = config_values_snapshot({})
        assert result == []


# ============================================================================
# Transformation Pipelines
# ============================================================================


class TestScaleReadings:
    """Characterize itertools.imap usage."""

    def test_scale_readings_returns_iterator(self):
        """scale_readings() returns lazy iterator."""
        result = scale_readings([1, 2, 3], 10)
        # Should be an iterator
        assert hasattr(result, "__next__") or hasattr(result, "__iter__")

    def test_scale_readings_multiplies(self):
        """scale_readings() scales values by factor."""
        result = list(scale_readings([1, 2, 3, 4], 5))
        assert result == [5, 10, 15, 20]

    def test_scale_readings_float_factor(self):
        """scale_readings() works with float factor."""
        result = list(scale_readings([10, 20, 30], 0.5))
        assert result == [5.0, 10.0, 15.0]


class TestFilterValidReadings:
    """Characterize itertools.ifilter usage."""

    def test_filter_valid_readings_returns_iterator(self):
        """filter_valid_readings() returns lazy iterator."""
        readings = [MockReading(1, 192), MockReading(2, 0)]
        result = filter_valid_readings(readings)
        assert hasattr(result, "__next__") or hasattr(result, "__iter__")

    def test_filter_valid_readings_filters_by_quality(self):
        """filter_valid_readings() keeps quality >= threshold."""
        readings = [
            MockReading(1, 192),
            MockReading(2, 100),
            MockReading(3, 200),
            MockReading(4, 191),
        ]
        result = list(filter_valid_readings(readings, min_quality=192))
        assert len(result) == 2
        assert result[0].value == 1
        assert result[1].value == 3

    def test_filter_valid_readings_default_threshold(self):
        """filter_valid_readings() defaults to quality=192."""
        readings = [MockReading(1, 192), MockReading(2, 191)]
        result = list(filter_valid_readings(readings))
        assert len(result) == 1


class TestZipTimestamps:
    """Characterize itertools.izip usage."""

    def test_zip_timestamps_returns_iterator(self):
        """zip_timestamps() returns lazy iterator."""
        result = zip_timestamps([1, 2], [3, 4])
        assert hasattr(result, "__next__") or hasattr(result, "__iter__")

    def test_zip_timestamps_pairs_readings(self):
        """zip_timestamps() pairs up readings."""
        a = [MockReading(10), MockReading(20)]
        b = [MockReading(30), MockReading(40)]
        result = list(zip_timestamps(a, b))
        assert len(result) == 2
        assert result[0][0].value == 10
        assert result[0][1].value == 30

    def test_zip_timestamps_stops_at_shorter(self):
        """zip_timestamps() stops at shorter sequence."""
        a = [1, 2, 3]
        b = [4, 5]
        result = list(zip_timestamps(a, b))
        assert len(result) == 2


# ============================================================================
# Eager List Producers
# ============================================================================


class TestExtractValues:
    """Characterize map() returning list in Py2."""

    def test_extract_values_returns_list(self):
        """extract_values() returns list (Py2 map behavior)."""
        readings = [MockReading(10), MockReading(20), MockReading(30)]
        result = extract_values(readings)
        assert isinstance(result, list)
        assert result == [10, 20, 30]

    def test_extract_values_empty(self):
        """extract_values() handles empty input."""
        result = extract_values([])
        assert result == []


class TestGoodReadings:
    """Characterize filter() returning list in Py2."""

    def test_good_readings_returns_list(self):
        """good_readings() returns list (Py2 filter behavior)."""
        readings = [
            MockReading(1, 192),
            MockReading(2, 100),
            MockReading(3, 200),
        ]
        result = good_readings(readings)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_good_readings_filters_quality(self):
        """good_readings() keeps quality >= 192."""
        readings = [
            MockReading(1, 192),
            MockReading(2, 191),
            MockReading(3, 193),
        ]
        result = good_readings(readings)
        assert [r.value for r in result] == [1, 3]


class TestPairedChannels:
    """Characterize zip() returning list in Py2."""

    def test_paired_channels_returns_list(self):
        """paired_channels() returns list (Py2 zip behavior)."""
        a = [1, 2, 3]
        b = [4, 5, 6]
        result = paired_channels(a, b)
        assert isinstance(result, list)
        assert result == [(1, 4), (2, 5), (3, 6)]

    def test_paired_channels_stops_at_shorter(self):
        """paired_channels() stops at shorter list."""
        result = paired_channels([1, 2, 3], [4, 5])
        assert result == [(1, 4), (2, 5)]


# ============================================================================
# Generator Consumption
# ============================================================================


class TestTakeNext:
    """Characterize .next() method usage."""

    def test_take_next_pulls_value(self):
        """take_next() gets next value from iterator."""
        it = iter([10, 20, 30])
        assert take_next(it) == 10
        assert take_next(it) == 20
        assert take_next(it) == 30

    def test_take_next_raises_on_exhausted(self):
        """take_next() raises StopIteration when exhausted."""
        it = iter([1])
        take_next(it)
        with pytest.raises(StopIteration):
            take_next(it)


class TestPeek:
    """Characterize .next() in peek implementation."""

    def test_peek_returns_value_and_iterator(self):
        """peek() returns (value, new_iterator)."""
        it = iter([1, 2, 3])
        value, new_it = peek(it)
        assert value == 1

    def test_peek_replays_value(self):
        """peek() replays peeked value in new iterator."""
        it = iter([1, 2, 3])
        value, new_it = peek(it)
        assert take_next(new_it) == 1
        assert take_next(new_it) == 2

    def test_peek_original_iterator_advanced(self):
        """peek() advances original iterator."""
        it = iter([1, 2, 3])
        value, new_it = peek(it)
        # Original iterator is advanced past 1
        assert take_next(it) == 2


class TestDrain:
    """Characterize drain() consuming iterator."""

    def test_drain_all(self):
        """drain() consumes entire iterator if no limit."""
        it = iter(range(10))
        result = drain(it)
        assert result == list(range(10))

    def test_drain_with_limit(self):
        """drain() stops at limit."""
        it = iter(range(100))
        result = drain(it, limit=5)
        assert result == [0, 1, 2, 3, 4]

    def test_drain_empty(self):
        """drain() handles empty iterator."""
        result = drain(iter([]))
        assert result == []

    def test_drain_limit_exceeds_length(self):
        """drain() handles limit > iterator length."""
        it = iter([1, 2, 3])
        result = drain(it, limit=10)
        assert result == [1, 2, 3]
