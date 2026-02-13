# -*- coding: utf-8 -*-
"""
Tests for mainframe batch parser: EBCDIC, COMP-3 packed decimal,
fixed-width fields, CopybookLayout, MainframeRecord.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.data_processing.mainframe_parser import (
    decode_comp3, decode_binary_field, decode_zoned_decimal,
    CopybookLayout, MainframeRecord, EBCDIC_CODEC,
)
from src.core.exceptions import ParseError
from tests.conftest import make_comp3_bytes


class TestEbcdicDecoding(unittest.TestCase):

    def test_roundtrip(self):
        original = "HELLO WORLD"
        self.assertEqual(original.encode(EBCDIC_CODEC).decode(EBCDIC_CODEC), original)
        print("EBCDIC roundtrip OK")

    def test_space_is_0x40(self):
        self.assertEqual(ord(" ".encode(EBCDIC_CODEC)), 0x40)

    def test_padded_field_rstrip(self):
        padded = "SMITH".encode(EBCDIC_CODEC) + (" " * 35).encode(EBCDIC_CODEC)
        self.assertEqual(padded.decode(EBCDIC_CODEC).rstrip(), "SMITH")


class TestComp3PackedDecimal(unittest.TestCase):

    def test_positive(self):
        result = decode_comp3(b"\x01\x23\x45\x3C")
        self.assertIsInstance(result, int)
        self.assertTrue(result > 0)
        print("COMP-3 positive: %d" % result)

    def test_negative(self):
        result = decode_comp3(b"\x04\x2D")
        self.assertTrue(result < 0)
        self.assertIsInstance(result, int)

    def test_zero(self):
        self.assertEqual(decode_comp3(b"\x0C"), 0)

    def test_empty_raises(self):
        self.assertRaises(ParseError, decode_comp3, b"")

    def test_large_account(self):
        result = decode_comp3(b"\x00\x12\x34\x56\x78\x9C")
        self.assertIsInstance(result, int)

    def test_conftest_helper(self):
        raw = make_comp3_bytes(99, num_bytes=2)
        self.assertIsInstance(decode_comp3(raw), int)


class TestDecodeBinaryField(unittest.TestCase):

    def test_signed_halfword(self):
        self.assertEqual(decode_binary_field(struct.pack(">h", -1234)), -1234)

    def test_unsigned_halfword(self):
        self.assertEqual(decode_binary_field(struct.pack(">H", 65535), signed=False), 65535)

    def test_doubleword(self):
        raw = struct.pack(">q", 9999999999)
        self.assertEqual(decode_binary_field(raw), 9999999999)
        print("Doubleword: %d" % decode_binary_field(raw))

    def test_unsupported_length(self):
        self.assertRaises(ParseError, decode_binary_field, b"\x01\x02\x03")


class TestDecodeZonedDecimal(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(decode_zoned_decimal(b""), 0)

    def test_positive(self):
        result = decode_zoned_decimal(b"\xF1\xF2\xF3\xC4")
        self.assertEqual(result, 1234)
        self.assertIsInstance(result, int)

    def test_negative(self):
        self.assertEqual(decode_zoned_decimal(b"\xF5\xD6"), -56)


class TestCopybookLayout(unittest.TestCase):

    def setUp(self):
        self.layout = CopybookLayout("TEST-LAYOUT", 100)
        self.layout.add_field("ACCOUNT-NO", 0, 6, "comp3")
        self.layout.add_field("CUST-NAME", 6, 40, "char")

    def test_field_names(self):
        self.assertEqual(self.layout.field_names(), ["ACCOUNT-NO", "CUST-NAME"])

    def test_get_field(self):
        self.assertEqual(self.layout.get_field("CUST-NAME")["offset"], 6)

    def test_unknown_raises(self):
        self.assertRaises(ParseError, self.layout.get_field, "BOGUS")
        print("ParseError for unknown field")


class TestMainframeRecord(unittest.TestCase):

    def setUp(self):
        self.record = MainframeRecord(0, b"\x00" * 50, CopybookLayout("R", 50))

    def test_set_get(self):
        self.record.set_field("NAME", "JONES")
        self.assertEqual(self.record.get("NAME"), "JONES")

    def test_missing_default(self):
        self.assertEqual(self.record.get("X", "N/A"), "N/A")

    def test_errors(self):
        self.assertFalse(self.record.has_errors())
        self.record.add_error("Bad")
        self.assertTrue(self.record.has_errors())

    def test_as_dict(self):
        self.record.set_field("A", 1)
        self.assertEqual(self.record.as_dict()["A"], 1)

    def test_account_is_long(self):
        self.record.set_field("ACCT", 9876543210)
        self.assertIsInstance(self.record.get("ACCT"), int)
        print("Account stored as int")


if __name__ == "__main__":
    unittest.main()
