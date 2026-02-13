# -*- coding: utf-8 -*-
"""
Tests for CSV processor: unicode_csv_reader, CsvFieldMapper,
StringIO-based parsing, encode/decode chains.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from io import StringIO
from src.data_processing.csv_processor import (
    unicode_csv_reader, unicode_csv_writer, CsvFieldMapper,
    _BOM_UTF8, _BOM_UTF16_LE,
)
from tests.conftest import assert_unicode


class TestUnicodeCsvReader(unittest.TestCase):

    def test_basic_utf8(self):
        rows = list(unicode_csv_reader(StringIO("name,value\nA,1\nB,2\n")))
        self.assertEqual(len(rows), 3)
        for cell in rows[1]:
            assert_unicode(self, cell)
        print("UTF-8 CSV: %d rows" % len(rows))

    def test_latin1_degree_sign(self):
        csv_bytes = ("Tag,Temp\u00b0C\nT-01,23.5\n").encode("latin-1")
        rows = list(unicode_csv_reader(StringIO(csv_bytes.decode("latin-1"))))
        self.assertIn("\u00b0", rows[0][1])

    def test_empty(self):
        self.assertEqual(list(unicode_csv_reader(StringIO(""))), [])

    def test_japanese(self):
        text = "sensor,label\nS1,\u6e29\u5ea6\n"
        rows = list(unicode_csv_reader(StringIO(text)))
        self.assertEqual(rows[1][1], "\u6e29\u5ea6")

    def test_quoted(self):
        rows = list(unicode_csv_reader(StringIO('a,b\nV,"X, Y"\n')))
        self.assertEqual(rows[1][1], "X, Y")


class TestUnicodeCsvWriter(unittest.TestCase):

    def test_write_unicode(self):
        buf = StringIO()
        unicode_csv_writer(buf).writerow(["Tag", "\u00b0C"])
        self.assertIsInstance(buf.getvalue(), str)
        print("CSV written")

    def test_mixed_types(self):
        buf = StringIO()
        unicode_csv_writer(buf).writerow(["s", "v", 42])
        self.assertIn("42", buf.getvalue())

    def test_writerows(self):
        buf = StringIO()
        unicode_csv_writer(buf).writerows([["a", "b"], ["c", "d"]])
        self.assertEqual(len(buf.getvalue().strip().split("\r\n")), 2)


class TestCsvFieldMapper(unittest.TestCase):

    def setUp(self):
        self.m = CsvFieldMapper()
        self.m.add_mapping("Time", "timestamp")
        self.m.add_mapping("Zeitstempel", "timestamp")
        self.m.add_mapping("Value", "reading")
        self.m.add_mapping("Tag", "sensor_id")

    def test_map_header(self):
        self.assertEqual(self.m.map_header(["Tag", "Time", "Value"]),
                         ["sensor_id", "timestamp", "reading"])

    def test_case_insensitive(self):
        self.assertEqual(self.m.map_header(["TIME"])[0], "timestamp")

    def test_unknown_passthrough(self):
        self.assertEqual(self.m.map_header(["Tag", "Extra"])[1], "Extra")

    def test_byte_header(self):
        self.assertEqual(self.m.map_header(["Tag"])[0], "sensor_id")

    def test_transform(self):
        self.m.add_mapping("raw", "temp", lambda v: float(v) / 10.0)
        self.assertAlmostEqual(self.m.transform_value("temp", "235"), 23.5)


class TestEncodingRoundtrips(unittest.TestCase):

    def test_bom_constants(self):
        self.assertEqual(_BOM_UTF8, b"\xef\xbb\xbf")
        self.assertEqual(_BOM_UTF16_LE, b"\xff\xfe")

    def test_utf8_roundtrip(self):
        original = "caf\xe9"
        self.assertEqual(original.encode("utf-8").decode("utf-8"), original)
        print("UTF-8 roundtrip OK")

    def test_latin1_roundtrip(self):
        original = "Stra\u00dfe"
        self.assertEqual(original.encode("latin-1").decode("latin-1"), original)

    def test_utf8_to_latin1_chain(self):
        text = "\xe9"
        self.assertEqual(text.encode("utf-8").decode("utf-8").encode("latin-1"), b"\xe9")


if __name__ == "__main__":
    unittest.main()
