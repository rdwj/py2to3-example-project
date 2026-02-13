# -*- coding: utf-8 -*-
"""
Core data types for the Legacy Industrial Data Platform.

Defines the foundational value objects used across all subsystems:
sensor readings, data points, counters, and the registry machinery
that automatically tracks every sensor type in the running system.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import time
import struct

# ---------------------------------------------------------------------------
# Sensor-type registry -- populated automatically by the SensorMeta metaclass
# ---------------------------------------------------------------------------

_sensor_registry = {}


class SensorMeta(type):
    """Metaclass that registers every SensorReading subclass by its
    ``sensor_type`` class attribute so that incoming packets can be
    dispatched to the right handler without a manual mapping table."""

    def __new__(mcs, name, bases, namespace):
        cls = type.__new__(mcs, name, bases, namespace)
        sensor_type = namespace.get("sensor_type")
        if sensor_type is not None:
            _sensor_registry[sensor_type] = cls
        return cls


def get_sensor_class(sensor_type):
    """Look up the SensorReading subclass for *sensor_type*."""
    return _sensor_registry[sensor_type]


# ---------------------------------------------------------------------------
# DataPoint -- old-style class (no explicit base)
# ---------------------------------------------------------------------------

@functools.total_ordering
class DataPoint(object):
    """A single timestamped measurement from any source.

    Old-style class intentionally -- this code predates the project's
    adoption of new-style classes.
    """

    __slots__ = ("tag", "value", "timestamp", "quality")

    def __init__(self, tag, value, timestamp=None, quality=192):
        self.tag = tag
        self.value = value
        self.timestamp = timestamp or time.time()
        self.quality = quality

    def __eq__(self, other):
        """Order data points chronologically, then by tag name."""
        return self.timestamp == other.timestamp and self.tag == other.tag

    def __lt__(self, other):
        """Order data points chronologically, then by tag name."""
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.tag < other.tag

    def __bool__(self):
        """A data point is 'truthy' when its quality code indicates good
        data (OPC quality >= 192)."""
        return self.quality >= 192

    def __truediv__(self, scalar):
        """Scale the measured value down -- used for unit conversion
        (e.g. mbar to kPa)."""
        return DataPoint(
            self.tag,
            self.value / scalar,
            self.timestamp,
            self.quality,
        )

    def __repr__(self):
        return "DataPoint(%r, %r, ts=%.3f, q=%d)" % (
            self.tag, self.value, self.timestamp, self.quality,
        )


# ---------------------------------------------------------------------------
# SensorReading -- new-style class with auto-registration metaclass
# ---------------------------------------------------------------------------

class SensorReading(object, metaclass=SensorMeta):
    """Base class for typed sensor readings.

    Subclasses set ``sensor_type`` and get registered automatically so
    the protocol layer can map a raw type byte to the right class.
    """

    sensor_type = None          # subclasses override

    def __init__(self, sensor_id, raw_bytes, timestamp=None):
        self.sensor_id = sensor_id
        self.raw_bytes = raw_bytes
        self.timestamp = timestamp or time.time()
        self.decoded_value = self._decode(raw_bytes)

    def _decode(self, raw_bytes):
        """Override in subclasses to unpack the raw payload."""
        return None

    def as_data_point(self):
        return DataPoint(self.sensor_id, self.decoded_value, self.timestamp)


class TemperatureReading(SensorReading):
    sensor_type = 0x01

    def _decode(self, raw_bytes):
        # Two-byte signed integer, big-endian, in tenths of a degree C
        if len(raw_bytes) >= 2:
            raw_val = struct.unpack(">h", raw_bytes[:2])[0]
            return raw_val / 10.0
        return None


class PressureReading(SensorReading):
    sensor_type = 0x02

    def _decode(self, raw_bytes):
        # Four-byte unsigned int, big-endian, in Pascals
        if len(raw_bytes) >= 4:
            return struct.unpack(">I", raw_bytes[:4])[0]
        return None


class FlowReading(SensorReading):
    sensor_type = 0x03

    def _decode(self, raw_bytes):
        # Four-byte float, big-endian, litres/minute
        if len(raw_bytes) >= 4:
            return struct.unpack(">f", raw_bytes[:4])[0]
        return None


class VibrationReading(SensorReading):
    sensor_type = 0x04

    def _decode(self, raw_bytes):
        # Two unsigned shorts: frequency_hz, amplitude_mm_s_x100
        if len(raw_bytes) >= 4:
            freq, amp = struct.unpack(">HH", raw_bytes[:4])
            return {"frequency_hz": freq, "amplitude_mm_s": amp / 100.0}
        return None


# ---------------------------------------------------------------------------
# LargeCounter -- uses long type for 64-bit event counters
# ---------------------------------------------------------------------------

class LargeCounter(object):
    """Monotonically increasing 64-bit counter for high-throughput
    event tracking (totaliser pulses, packet counts, etc.).

    Uses ``long`` literals to guarantee arbitrary precision even on
    32-bit builds where plain ``int`` rolls over at 2**31.
    """

    MAX_VALUE = 18446744073709551615   # 2**64 - 1

    def __init__(self, initial=0):
        if not isinstance(initial, int):
            raise TypeError("counter value must be an integer, got %s" % type(initial).__name__)
        self._value = int(initial)

    @property
    def value(self):
        return self._value

    def increment(self, amount=1):
        self._value = (self._value + int(amount)) % (self.MAX_VALUE + 1)

    def __repr__(self):
        return "LargeCounter(%d)" % self._value

    def __int__(self):
        return self._value


# ---------------------------------------------------------------------------
# Comparison / sorting helpers
# ---------------------------------------------------------------------------

def _compare_by_timestamp(a, b):
    """cmp-style comparator for DataPoint sorting."""
    return (a.timestamp > b.timestamp) - (a.timestamp < b.timestamp)


def sort_data_points(points):
    """Return *points* sorted chronologically using a custom cmp function."""
    return sorted(points, key=functools.cmp_to_key(_compare_by_timestamp))


# ---------------------------------------------------------------------------
# Type-checking helpers -- used throughout the platform to guard against
# bytes/unicode confusion at API boundaries.
# ---------------------------------------------------------------------------

def is_string(value):
    """Return True if *value* is any kind of string (byte or unicode)."""
    return isinstance(value, (str, bytes))


def is_text(value):
    """Return True if *value* is a unicode string."""
    return isinstance(value, str)


def is_binary(value):
    """Return True if *value* is a byte string."""
    return isinstance(value, bytes)


# ---------------------------------------------------------------------------
# Efficient binary data views
# ---------------------------------------------------------------------------

def register_view(raw_data, offset, length):
    """Return a zero-copy view into *raw_data* for a MODBUS register
    block without allocating a new string.  Uses ``buffer()`` which
    maps to ``memoryview`` in Python 3."""
    return memoryview(raw_data)[offset:offset + length]
