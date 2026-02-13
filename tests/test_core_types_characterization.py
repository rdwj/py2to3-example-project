# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/types.py

Captures pre-migration behavior of:
- DataPoint old-style class with __cmp__, __nonzero__, __div__
- SensorReading metaclass registration via __metaclass__
- LargeCounter with long literals and __long__
- cmp() builtin and sorted(cmp=) keyword
- buffer() builtin for zero-copy views
- basestring/unicode type checks
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.types import (
    DataPoint, SensorReading, TemperatureReading, PressureReading,
    FlowReading, VibrationReading, LargeCounter,
    sort_data_points, is_string, is_text, is_binary,
    register_view, get_sensor_class, _compare_by_timestamp,
)


# ---------------------------------------------------------------------------
# DataPoint
# ---------------------------------------------------------------------------

class TestDataPoint:
    """Characterize the old-style DataPoint class."""

    def test_construction(self):
        """Captures: DataPoint holds tag, value, timestamp, quality."""
        dp = DataPoint("TEMP-001", 23.5, timestamp=1000.0, quality=192)
        assert dp.tag == "TEMP-001"
        assert dp.value == 23.5
        assert dp.timestamp == 1000.0
        assert dp.quality == 192

    @pytest.mark.py2_behavior
    def test_cmp_by_timestamp(self):
        """Captures: __cmp__ orders by timestamp then tag.
        cmp() builtin and __cmp__ removed in Py3; use __lt__/__eq__."""
        dp1 = DataPoint("A", 1, timestamp=100.0)
        dp2 = DataPoint("B", 2, timestamp=200.0)
        assert cmp(dp1, dp2) < 0
        assert cmp(dp2, dp1) > 0

    @pytest.mark.py2_behavior
    def test_cmp_same_timestamp_by_tag(self):
        """Captures: same timestamp falls through to tag comparison."""
        dp1 = DataPoint("A", 1, timestamp=100.0)
        dp2 = DataPoint("B", 2, timestamp=100.0)
        assert cmp(dp1, dp2) < 0

    @pytest.mark.py2_behavior
    def test_nonzero_good_quality(self):
        """Captures: __nonzero__ returns True for quality >= 192.
        Renamed __bool__ in Py3."""
        dp = DataPoint("T", 1, quality=192)
        assert bool(dp) is True

    @pytest.mark.py2_behavior
    def test_nonzero_bad_quality(self):
        """Captures: __nonzero__ returns False for quality < 192."""
        dp = DataPoint("T", 1, quality=0)
        assert bool(dp) is False

    @pytest.mark.py2_behavior
    def test_div_scales_value(self):
        """Captures: __div__ produces new DataPoint with scaled value.
        __div__ used for classic division in Py2; Py3 uses __truediv__."""
        dp = DataPoint("P", 101325.0, timestamp=1000.0, quality=192)
        result = dp / 1000.0
        assert abs(result.value - 101.325) < 0.001
        assert result.tag == "P"
        assert result.timestamp == 1000.0

    def test_repr(self):
        """Captures: __repr__ format."""
        dp = DataPoint("T", 23.5, timestamp=1000.0, quality=192)
        r = repr(dp)
        assert "DataPoint" in r
        assert "T" in r


# ---------------------------------------------------------------------------
# SensorReading subclasses
# ---------------------------------------------------------------------------

class TestSensorReadings:
    """Characterize sensor reading type dispatch."""

    @pytest.mark.py2_behavior
    def test_metaclass_registration(self):
        """Captures: __metaclass__ = SensorMeta auto-registers types.
        Py3 uses class Foo(SensorReading, metaclass=SensorMeta)."""
        assert get_sensor_class(0x01) is TemperatureReading
        assert get_sensor_class(0x02) is PressureReading
        assert get_sensor_class(0x03) is FlowReading
        assert get_sensor_class(0x04) is VibrationReading

    def test_temperature_decode(self):
        """Captures: 2-byte big-endian signed, tenths of degree C."""
        raw = struct.pack(">h", 235)
        reading = TemperatureReading("S001", raw, timestamp=1000.0)
        assert abs(reading.decoded_value - 23.5) < 0.01

    def test_pressure_decode(self):
        """Captures: 4-byte big-endian unsigned, Pascals."""
        raw = struct.pack(">I", 101325)
        reading = PressureReading("S002", raw, timestamp=1000.0)
        assert reading.decoded_value == 101325

    def test_flow_decode(self):
        """Captures: 4-byte big-endian float, litres/minute."""
        raw = struct.pack(">f", 42.5)
        reading = FlowReading("S003", raw, timestamp=1000.0)
        assert abs(reading.decoded_value - 42.5) < 0.1

    def test_vibration_decode(self):
        """Captures: two unsigned shorts: freq_hz, amplitude_mm_s."""
        raw = struct.pack(">HH", 120, 350)
        reading = VibrationReading("S004", raw, timestamp=1000.0)
        assert reading.decoded_value["frequency_hz"] == 120
        assert abs(reading.decoded_value["amplitude_mm_s"] - 3.5) < 0.01

    def test_as_data_point(self):
        """Captures: as_data_point creates DataPoint from reading."""
        raw = struct.pack(">h", 235)
        reading = TemperatureReading("S001", raw, timestamp=1000.0)
        dp = reading.as_data_point()
        assert dp.tag == "S001"
        assert abs(dp.value - 23.5) < 0.01


# ---------------------------------------------------------------------------
# LargeCounter
# ---------------------------------------------------------------------------

class TestLargeCounter:
    """Characterize 64-bit counter with long type."""

    @pytest.mark.py2_behavior
    def test_construction_with_long(self):
        """Captures: initial value stored as long(). long removed in Py3."""
        counter = LargeCounter(0)
        assert counter.value == 0

    @pytest.mark.py2_behavior
    def test_increment_with_long_literal(self):
        """Captures: increment(1L) uses long literals."""
        counter = LargeCounter()
        counter.increment(1)
        assert counter.value == 1

    @pytest.mark.py2_behavior
    def test_max_value_long_literal(self):
        """Captures: MAX_VALUE is 2**64-1 as long literal."""
        assert LargeCounter.MAX_VALUE == 18446744073709551615

    def test_wraps_on_overflow(self):
        """Captures: counter wraps at MAX_VALUE + 1."""
        counter = LargeCounter(LargeCounter.MAX_VALUE)
        counter.increment(1)
        assert counter.value == 0

    @pytest.mark.py2_behavior
    def test_long_method(self):
        """Captures: __long__ returns counter value. Removed in Py3."""
        counter = LargeCounter(42)
        assert int(counter) == 42

    def test_type_check_on_init(self):
        """Captures: non-integer raises TypeError."""
        with pytest.raises(TypeError):
            LargeCounter("not an int")


# ---------------------------------------------------------------------------
# Sorting and type checks
# ---------------------------------------------------------------------------

class TestSortingAndTypeChecks:
    """Characterize sorting with cmp= and type-checking helpers."""

    @pytest.mark.py2_behavior
    def test_sort_data_points_with_cmp(self):
        """Captures: sorted(cmp=) keyword argument.
        cmp= removed from sorted() in Py3; use key= or functools.cmp_to_key."""
        points = [
            DataPoint("A", 1, timestamp=300.0),
            DataPoint("B", 2, timestamp=100.0),
            DataPoint("C", 3, timestamp=200.0),
        ]
        result = sort_data_points(points)
        assert result[0].timestamp == 100.0
        assert result[-1].timestamp == 300.0

    @pytest.mark.py2_behavior
    def test_is_string(self):
        """Captures: isinstance(value, basestring). basestring removed in Py3."""
        assert is_string("bytes") is True
        assert is_string(u"unicode") is True
        assert is_string(42) is False

    @pytest.mark.py2_behavior
    def test_is_text(self):
        """Captures: isinstance(value, unicode). unicode removed in Py3."""
        assert is_text(u"text") is True
        assert is_text("bytes") is False

    @pytest.mark.py2_behavior
    def test_is_binary(self):
        """Captures: isinstance(value, str) and not isinstance(value, unicode)."""
        assert is_binary("bytes") is True
        assert is_binary(u"text") is False

    @pytest.mark.py2_behavior
    def test_register_view(self):
        """Captures: buffer() builtin for zero-copy views.
        buffer() -> memoryview() in Py3."""
        data = "\x00\x01\x02\x03\x04\x05"
        view = register_view(data, 2, 3)
        assert str(view) == "\x02\x03\x04"
