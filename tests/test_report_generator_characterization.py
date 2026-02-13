# -*- coding: utf-8 -*-
"""
Characterization tests for src/reporting/report_generator.py

Captures pre-migration behavior of:
- ReportSection with basestring/unicode checks
- ReportTemplate with exec statement and print >>sys.stderr
- ReportGenerator daily summary, alarm report, trend report
- Py2-specific: basestring, unicode, reduce() builtin, (int, float, long),
  exec statement, print >>stderr, dict.iteritems(),
  unicode() constructor, isinstance checks
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.reporting.report_generator import (
    ReportSection, ReportTemplate, ReportGenerator, ReportError,
)


# ---------------------------------------------------------------------------
# ReportSection
# ---------------------------------------------------------------------------

class TestReportSection:
    """Characterize report section construction and rendering."""

    def test_construction_with_unicode_title(self):
        """Captures: unicode title stored directly."""
        section = ReportSection(u"Test Section \u2014 Data")
        assert section.title == u"Test Section \u2014 Data"
        assert section.content_lines == []

    @pytest.mark.py2_behavior
    def test_construction_with_str_title(self):
        """Captures: str title decoded via safe_decode().
        isinstance(title, basestring) check; basestring removed in Py3."""
        section = ReportSection("ASCII Title")
        assert section.title is not None

    def test_construction_with_non_string(self):
        """Captures: non-string title converted via unicode()."""
        section = ReportSection(42)
        assert section.title == u"42"

    def test_add_line_unicode(self):
        """Captures: unicode lines appended directly."""
        section = ReportSection(u"Test")
        section.add_line(u"Line with caf\u00e9")
        assert len(section.content_lines) == 1
        assert u"caf\u00e9" in section.content_lines[0]

    @pytest.mark.py2_behavior
    def test_add_line_str_decoded(self):
        """Captures: str lines decoded via safe_decode().
        isinstance(line, basestring) branch."""
        section = ReportSection(u"Test")
        section.add_line("plain str line")
        assert len(section.content_lines) == 1

    def test_add_line_non_string(self):
        """Captures: non-string converted via unicode()."""
        section = ReportSection(u"Test")
        section.add_line(42)
        assert section.content_lines[0] == u"42"

    def test_render(self):
        """Captures: render produces header + body separated by newline."""
        section = ReportSection(u"Header")
        section.add_line(u"line 1")
        section.add_line(u"line 2")
        rendered = section.render()
        assert u"=== Header ===" in rendered
        assert u"line 1" in rendered
        assert u"line 2" in rendered


# ---------------------------------------------------------------------------
# ReportTemplate
# ---------------------------------------------------------------------------

class TestReportTemplate:
    """Characterize template evaluation via exec."""

    @pytest.mark.py2_behavior
    def test_evaluate_simple(self):
        """Captures: exec statement form with namespace dict.
        Py2: exec code in namespace; Py3: exec(code, namespace)."""
        template = ReportTemplate("test", "lines.append('Hello')")
        result = template.evaluate({})
        assert result == ["Hello"]

    @pytest.mark.py2_behavior
    def test_evaluate_with_context(self):
        """Captures: context dict merged into exec namespace."""
        code = "lines.append('Site: %s' % site_name)"
        template = ReportTemplate("test", code)
        result = template.evaluate({"site_name": "Plant A"})
        assert result == ["Site: Plant A"]

    def test_evaluate_syntax_error(self):
        """Captures: SyntaxError wrapped in ReportError."""
        template = ReportTemplate("bad", "def :")
        with pytest.raises(ReportError, match="Bad template syntax"):
            template.evaluate({})

    def test_evaluate_runtime_error(self):
        """Captures: runtime errors wrapped in ReportError."""
        template = ReportTemplate("bad", "x = 1/0")
        with pytest.raises(ReportError, match="Template failed"):
            template.evaluate({})


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class TestReportGenerator:
    """Characterize report generation from sensor data."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(config={
            "site_name": u"Test Plant",
            "output_dir": "/tmp/reports",
        })

    @pytest.mark.py2_behavior
    def test_daily_summary_with_data_points(self, generator):
        """Captures: generate_daily_summary uses reduce() builtin,
        isinstance(r, (int, float, long)), dict.iteritems()."""
        from src.core.types import DataPoint
        sensor_data = {
            "TEMP-001": [
                DataPoint("TEMP-001", 23.5, timestamp=1000.0),
                DataPoint("TEMP-001", 24.0, timestamp=1001.0),
                DataPoint("TEMP-001", 22.8, timestamp=1002.0),
            ],
        }
        sections = generator.generate_daily_summary(sensor_data, "2024-01-15")
        assert len(sections) >= 2
        # Header section
        rendered = sections[0].render()
        assert u"Daily Summary" in rendered
        assert u"Test Plant" in rendered
        # Stats section
        stats_rendered = sections[1].render()
        assert u"TEMP-001" in stats_rendered

    @pytest.mark.py2_behavior
    def test_daily_summary_with_numeric_values(self, generator):
        """Captures: isinstance(r, (int, float, long)) for raw numbers.
        long removed in Py3."""
        sensor_data = {
            "FLOW-001": [10.0, 20.0, 30.0],
        }
        sections = generator.generate_daily_summary(sensor_data)
        stats = sections[1].render()
        assert u"FLOW-001" in stats

    def test_alarm_report(self, generator):
        """Captures: alarm report generation with severity filter."""
        alarms = [
            {"tag": "TEMP-001", "message": "High temperature", "severity": 3,
             "timestamp": time.time()},
            {"tag": "FLOW-001", "message": "Low flow", "severity": 1,
             "timestamp": time.time()},
        ]
        sections = generator.generate_alarm_report(alarms, severity_filter=2)
        assert len(sections) >= 2
        active = sections[1].render()
        assert "High temperature" in active
        # Low severity alarm should be filtered out
        assert "Low flow" not in active

    def test_alarm_report_no_filter(self, generator):
        """Captures: no severity filter includes all alarms."""
        alarms = [
            {"tag": "T1", "message": "msg1", "severity": 1, "timestamp": time.time()},
            {"tag": "T2", "message": "msg2", "severity": 5, "timestamp": time.time()},
        ]
        sections = generator.generate_alarm_report(alarms)
        active = sections[1].render()
        assert "msg1" in active
        assert "msg2" in active

    @pytest.mark.py2_behavior
    def test_trend_report(self, generator):
        """Captures: trend report uses reduce() and unicode arrows.
        dict.iteritems() for traversing trend data."""
        trend_data = {
            "TEMP-001": [(1000.0, 20.0), (1001.0, 22.0), (1002.0, 24.0)],
        }
        sections = generator.generate_trend_report(trend_data)
        assert len(sections) >= 2
        trends = sections[1].render()
        assert u"TEMP-001" in trends

    def test_render_report_default(self, generator):
        """Captures: render_report without template produces default output."""
        sections = [
            ReportSection(u"Header"),
            ReportSection(u"Body"),
        ]
        sections[0].add_line(u"line 1")
        output = generator.render_report(sections)
        assert generator.DEFAULT_TITLE in output
        assert u"Header" in output

    @pytest.mark.py2_behavior
    def test_render_report_with_template(self, generator):
        """Captures: render_report with registered template uses exec."""
        template = ReportTemplate("custom", "lines.append('Custom: %s' % site_name)")
        generator.register_template(template)
        sections = [ReportSection(u"Test")]
        output = generator.render_report(sections, template_name="custom")
        assert u"Custom: Test Plant" in output

    def test_register_template_wrong_type(self, generator):
        """Captures: non-ReportTemplate raises ReportError."""
        with pytest.raises(ReportError, match="Expected ReportTemplate"):
            generator.register_template("not a template")


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestReportGeneratorEncoding:
    """Test encoding edge cases in report generation."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(config={"site_name": u"caf\u00e9 Plant"})

    def test_section_with_unicode_content(self, generator):
        """Captures: unicode content flows through sections correctly."""
        section = ReportSection(u"r\u00e9sum\u00e9 Section")
        section.add_line(u"Temp: 23.5\u00b0C")
        rendered = section.render()
        assert u"\u00e9" in rendered
        assert u"\u00b0" in rendered

    @pytest.mark.py2_behavior
    def test_alarm_with_unicode_message(self, generator):
        """Captures: unicode in alarm messages handled by basestring checks."""
        alarms = [{
            "tag": u"SENSOR-\u00b0C",
            "message": u"Temp\u00e9rature \u00e9lev\u00e9e",
            "severity": 3,
            "timestamp": time.time(),
        }]
        sections = generator.generate_alarm_report(alarms)
        active = sections[1].render()
        assert u"\u00e9" in active

    @pytest.mark.py2_behavior
    def test_save_report_encodes_unicode(self, generator, tmp_path):
        """Captures: save_report encodes unicode to bytes via safe_encode.
        isinstance(content, basestring) check; basestring removed in Py3."""
        content = u"Report with caf\u00e9"
        filepath = str(tmp_path / "report.txt")
        generator._output_dir = str(tmp_path)
        generator.save_report(content, "report.txt")
        with open(filepath, "rb") as f:
            raw = f.read()
        assert b"caf" in raw
