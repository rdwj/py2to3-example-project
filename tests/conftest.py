# -*- coding: utf-8 -*-
"""
Shared test fixtures and helpers for the platform test suite.
These predate pytest adoption; plain functions called from setUp().
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))


def make_data_point(tag="TEMP-001", value=23.5, timestamp=None, quality=192):
    from src.core.types import DataPoint
    return DataPoint(tag, value, timestamp or time.time(), quality)


def make_sensor_bytes(raw_hex):
    return bytes.fromhex(raw_hex)


def make_unicode_tag(base=u"Sensor", suffix=u"\u00b0C"):
    return base + u"-" + suffix


def make_ebcdic_string(text):
    return text.encode("cp037")


def make_comp3_bytes(value, num_bytes=4):
    digits = "%0*d" % ((num_bytes * 2) - 1, abs(value))
    sign = "c" if value >= 0 else "d"
    return bytes.fromhex(digits + sign)


def setup_test_environment():
    print("Setting up test environment")
    os.environ.setdefault("PLATFORM_ENV", "test")
    os.environ.setdefault("PLATFORM_HOME", "/tmp/platform_test")


def teardown_test_environment():
    print("Tearing down test environment")
    for key in ("PLATFORM_ENV", "PLATFORM_HOME"):
        if key in os.environ:
            del os.environ[key]


def assert_unicode(tc, value, msg=None):
    tc.assertIsInstance(value, str, msg or "Expected str, got %s" % type(value))


def assert_byte_string(tc, value, msg=None):
    tc.assertIsInstance(value, bytes, msg or "Expected bytes, got %s" % type(value))
