# -*- coding: utf-8 -*-
"""
Tests for report generation: captured print output, exec templates,
unicode content, reduce() aggregation, print >>sys.stderr.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time
import unittest
from functools import reduce

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from io import StringIO
from src.reporting.report_generator import (
    ReportSection, ReportTemplate, ReportGenerator, ReportError,
)
from src.core.types import DataPoint
from tests.conftest import assert_unicode


class TestReportSection(unittest.TestCase):

    def test_unicode_title(self):
        assert_unicode(self, ReportSection(u"Summary \u2014 2024").title)

    def test_add_line_decodes_bytes(self):
        sec = ReportSection(u"S")
        sec.add_line("ASCII line")
        assert_unicode(self, sec.content_lines[0])

    def test_render(self):
        sec = ReportSection(u"Test")
        sec.add_line(u"Line one")
        self.assertIn(u"=== Test ===", sec.render())
        print("Section rendered")


class TestReportTemplate(unittest.TestCase):

    def test_exec_populates_lines(self):
        result = ReportTemplate("t", "lines.append('n=' + str(len(sections)))\n").evaluate({"sections": [1, 2]})
        self.assertIn("2", result[0])

    def test_syntax_error_raises(self):
        self.assertRaises(ReportError, ReportTemplate("bad", "not valid\n").evaluate, {})

    def test_stderr_on_failure(self):
        old = sys.stderr
        sys.stderr = StringIO()
        try:
            try:
                ReportTemplate("fail", "raise ValueError\n").evaluate({})
            except ReportError:
                pass
            self.assertIn("fail", sys.stderr.getvalue())
        finally:
            sys.stderr = old
        print("stderr captured")


class TestDailySummary(unittest.TestCase):

    def setUp(self):
        self.gen = ReportGenerator(config={"site_name": u"Test Plant"})

    def test_sections(self):
        data = {"T": [DataPoint("T", 22.0), DataPoint("T", 24.0)]}
        self.assertTrue(len(self.gen.generate_daily_summary(data, "2024-01-15")) >= 2)

    def test_reduce_aggregation(self):
        data = {"T": [DataPoint("T", v) for v in [10.0, 20.0, 30.0]]}
        self.assertIn("20.00", self.gen.generate_daily_summary(data, "2024-06-01")[1].render())

    def test_captured_stdout(self):
        old = sys.stdout
        sys.stdout = StringIO()
        try:
            self.gen.generate_daily_summary({"S": [DataPoint("S", 1.0)]}, "2024-03-01")
            self.assertIn("Daily summary generated", sys.stdout.getvalue())
        finally:
            sys.stdout = old
        print("stdout captured OK")


class TestAlarmReport(unittest.TestCase):

    def test_unicode_site(self):
        gen = ReportGenerator(config={"site_name": u"Werk M\u00fcnchen"})
        alarms = [{"tag": "X", "message": u"\u00dcber", "severity": 3, "timestamp": time.time()}]
        self.assertIn(u"M\u00fcnchen", u"\n".join(s.render() for s in gen.generate_alarm_report(alarms)))

    def test_severity_filter(self):
        alarms = [{"tag": "A", "message": "low", "severity": 1, "timestamp": 0},
                  {"tag": "B", "message": "high", "severity": 5, "timestamp": 0}]
        rendered = ReportGenerator().generate_alarm_report(alarms, severity_filter=3)[-1].render()
        self.assertNotIn("low", rendered)
        self.assertIn("high", rendered)


class TestRendering(unittest.TestCase):

    def setUp(self):
        self.gen = ReportGenerator(config={"site_name": u"Plant B"})

    def test_default(self):
        output = self.gen.render_report([ReportSection(u"H", [u"body"])])
        assert_unicode(self, output)
        self.assertIn(u"Industrial Data Platform", output)

    def test_with_template(self):
        self.gen.register_template(ReportTemplate("c", "for s in sections:\n    lines.append(s.title)\n"))
        self.assertIn(u"X", self.gen.render_report([ReportSection(u"X")], template_name="c"))

    def test_fallback_on_error(self):
        self.gen.register_template(ReportTemplate("broken", "raise RuntimeError\n"))
        old = sys.stderr
        sys.stderr = StringIO()
        try:
            output = self.gen.render_report([ReportSection(u"F")], template_name="broken")
        finally:
            sys.stderr = old
        self.assertIn(u"Industrial Data Platform", output)


class TestReduceBuiltin(unittest.TestCase):

    def test_sum(self):
        self.assertEqual(reduce(lambda a, b: a + b, [10, 20, 30], 0), 60)

    def test_min(self):
        self.assertEqual(reduce(lambda a, b: a if a < b else b, [5, 3, 8]), 3)

    def test_concat(self):
        result = reduce(lambda a, b: a + b, [u"A", u"|", u"B"])
        assert_unicode(self, result)
        print("reduce() OK")


if __name__ == "__main__":
    unittest.main()
