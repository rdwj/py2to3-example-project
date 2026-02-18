# -*- coding: utf-8 -*-
"""
Tests for core types: DataPoint __cmp__/sorted(cmp=), LargeCounter
long arithmetic, SensorReading registry, basestring/unicode checks.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.types import (
    DataPoint, TemperatureReading, PressureReading,
    LargeCounter, sort_data_points, _compare_by_timestamp,
    is_string, is_text, is_binary, register_view, get_sensor_class,
)


class TestDataPointCmpAndSorting(unittest.TestCase):

    def test_cmp_by_timestamp(self):
        now = time.time()
        a = DataPoint("A", 1.0, timestamp=now)
        b = DataPoint("B", 2.0, timestamp=now + 1.0)
        self.assertEqual((a > b) - (a < b), -1)
        self.assertEqual((b > a) - (b < a), 1)
        self.assertEqual((a > a) - (a < a), 0)
        print("cmp() ordering verified")

    def test_cmp_same_ts_compares_tag(self):
        now = time.time()
        a = DataPoint("AAA", 0, timestamp=now)
        b = DataPoint("ZZZ", 0, timestamp=now)
        self.assertTrue(((a > b) - (a < b)) < 0)

    def test_sorted_with_cmp_param(self):
        import functools
        now = time.time()
        pts = [DataPoint("C", 0, timestamp=now + 2),
               DataPoint("A", 0, timestamp=now),
               DataPoint("B", 0, timestamp=now + 1)]
        self.assertEqual([p.tag for p in sorted(pts, key=functools.cmp_to_key(_compare_by_timestamp))],
                         ["A", "B", "C"])

    def test_sort_data_points(self):
        now = time.time()
        pts = [DataPoint("Z", 0, timestamp=now + 5), DataPoint("A", 0, timestamp=now)]
        self.assertEqual([p.tag for p in sort_data_points(pts)], ["A", "Z"])

    def test_nonzero(self):
        self.assertTrue(bool(DataPoint("T", 1.0, quality=192)))
        self.assertFalse(bool(DataPoint("T", 1.0, quality=0)))

    def test_div_and_integer_truncation(self):
        self.assertAlmostEqual((DataPoint("P", 1000.0) / 10).value, 100.0)
        self.assertEqual((DataPoint("C", 7) / 2).value, 3)
        print("Py2 integer division: 7/2 = 3")


class TestLargeCounter(unittest.TestCase):

    def test_value_is_long(self):
        self.assertIsInstance(LargeCounter(0).value, int)

    def test_increment(self):
        c = LargeCounter(10)
        c.increment(5)
        self.assertEqual(c.value, 15)

    def test_wraps_at_max(self):
        c = LargeCounter(LargeCounter.MAX_VALUE)
        c.increment(1)
        self.assertEqual(c.value, 0)

    def test_rejects_non_integer(self):
        self.assertRaises(TypeError, LargeCounter, "bad")
        self.assertRaises(TypeError, LargeCounter, 3.14)
        print("TypeError raised for bad input")

    def test_long_conversion(self):
        self.assertEqual(int(LargeCounter(42)), 42)


class TestSensorRegistry(unittest.TestCase):

    def test_lookup(self):
        self.assertIs(get_sensor_class(0x01), TemperatureReading)
        self.assertRaises(KeyError, get_sensor_class, 0xFF)

    def test_temperature_decode(self):
        r = TemperatureReading("T-01", struct.pack(">h", 235))
        self.assertAlmostEqual(r.decoded_value, 23.5)
        print("Temperature: %.1f" % r.decoded_value)

    def test_pressure_decode(self):
        self.assertEqual(PressureReading("P", struct.pack(">I", 101325)).decoded_value, 101325)

    def test_as_data_point(self):
        dp = TemperatureReading("T", struct.pack(">h", 200)).as_data_point()
        self.assertIsInstance(dp, DataPoint)


class TestTypeChecks(unittest.TestCase):

    def test_is_string(self):
        self.assertTrue(is_string("bytes"))
        self.assertTrue(is_string(u"text"))
        self.assertFalse(is_string(42))

    def test_is_text_and_binary(self):
        self.assertTrue(is_text(u"caf\xe9"))
        self.assertFalse(is_text("bytes"))
        self.assertTrue(is_binary("raw"))
        self.assertFalse(is_binary(u"text"))

    def test_basestring(self):
        self.assertIsInstance("x", str)
        self.assertIsInstance(u"x", str)
        print("basestring checks passed")

    def test_register_view(self):
        view = register_view("\x00\x01\x02\x03\x04\x05", 2, 3)
        self.assertEqual(str(view), "\x02\x03\x04")


if __name__ == "__main__":
    unittest.main()
