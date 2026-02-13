# -*- coding: utf-8 -*-
"""
Report generation engine for the Legacy Industrial Data Platform.

Produces daily summaries, alarm reports, and trend analysis documents
from sensor data.  Report templates are evaluated dynamically via
``exec`` so that plant engineers can customise output without modifying
Python code -- a decision made in 2009 that nobody has revisited.
"""


import functools
import sys
import time
import os

from src.core.types import DataPoint, is_string
from src.core.string_helpers import safe_decode, safe_encode
from src.core.exceptions import PlatformError


class ReportError(PlatformError):
    """Raised when report generation or template evaluation fails."""
    pass


class ReportSection:
    """A single section of a generated report (header, data table, etc.).
    Carries a unicode title and a list of content lines."""

    def __init__(self, title, content_lines=None):
        if isinstance(title, str):
            self.title = safe_decode(title)
        else:
            self.title = str(title)
        self.content_lines = content_lines or []
        self.timestamp = time.time()

    def add_line(self, line):
        if isinstance(line, str):
            self.content_lines.append(safe_decode(line))
        else:
            self.content_lines.append(str(line))

    def render(self):
        header = "=== " + self.title + " ==="
        body = "\n".join(self.content_lines)
        return header + "\n" + body + "\n"


class ReportTemplate:
    """Wraps a template code string that gets ``exec``-ed at render time.

    Template code writes into a ``lines`` list in the exec namespace.
    Templates live in /opt/platform/templates/ and are version-controlled
    separately from this codebase.
    """

    def __init__(self, name, code_string, description=""):
        self.name = name
        self.code_string = code_string
        self.description = description

    def evaluate(self, context):
        """Execute the template code with *context* as the namespace."""
        namespace = {"lines": [], "time": time, "unicode": str}
        namespace.update(context)
        try:
            exec(self.code_string, namespace)
        except SyntaxError as e:
            print(f"Template syntax error in '{self.name}': {e}", file=sys.stderr)
            raise ReportError(f"Bad template syntax: {e}")
        except Exception as e:
            print(f"Template execution error in '{self.name}': {e}", file=sys.stderr)
            raise ReportError(f"Template failed: {e}")
        return namespace["lines"]


class ReportGenerator:
    """Generates reports from sensor data and alarm history.

    Supports daily summaries, alarm digests, and trend analysis.
    """

    DEFAULT_TITLE = "Industrial Data Platform \u2014 Report"

    def __init__(self, config=None):
        self.config = config or {}
        self.templates = {}
        self._output_dir = self.config.get("output_dir", "/var/platform/reports")
        self._site_name = self.config.get("site_name", "Plant A")

    def register_template(self, template):
        if not isinstance(template, ReportTemplate):
            raise ReportError(f"Expected ReportTemplate, got {type(template).__name__}")
        self.templates[template.name] = template

    def generate_daily_summary(self, sensor_data, report_date=None):
        """Build a daily summary from a dict of sensor_tag -> readings."""
        if report_date is None:
            report_date = time.strftime("%Y-%m-%d")

        sections = []
        header = ReportSection("Daily Summary \u2014 " + str(report_date))
        header.add_line("Site: " + self._site_name)
        header.add_line("Generated: " + str(time.strftime("%Y-%m-%d %H:%M:%S")))
        header.add_line(f"Total sensors reporting: {len(sensor_data)}")
        sections.append(header)

        stats = ReportSection("Sensor Statistics")
        for tag, readings in sensor_data.items():
            values = []
            for r in readings:
                if isinstance(r, DataPoint):
                    values.append(r.value)
                elif isinstance(r, (int, float)):
                    values.append(r)
            if not values:
                continue

            total = functools.reduce(lambda a, b: a + b, values, 0.0)
            avg = total / len(values)
            min_val = functools.reduce(lambda a, b: a if a < b else b, values)
            max_val = functools.reduce(lambda a, b: a if a > b else b, values)

            tag_label = safe_decode(tag) if not isinstance(tag, str) else tag
            line = "  " + tag_label + ": "
            line = line + f"avg={avg:.2f}, min={min_val:.2f}, max={max_val:.2f}, n={len(values)}"
            stats.add_line(line)

        sections.append(stats)
        print(f"Daily summary generated for {report_date} ({len(sensor_data)} sensors)")
        return sections

    def generate_alarm_report(self, alarms, severity_filter=None):
        """Build a report of active alarms."""
        sections = []
        title_sec = ReportSection("Alarm Report")
        title_sec.add_line("Site: " + self._site_name)
        title_sec.add_line("Report time: " + str(time.strftime("%Y-%m-%d %H:%M:%S")))
        sections.append(title_sec)

        if severity_filter is not None:
            alarms = [a for a in alarms if a.get("severity", 0) >= severity_filter]

        active = ReportSection(f"Active Alarms ({len(alarms)})")
        for alarm in alarms:
            msg = alarm.get("message", "")
            if not isinstance(msg, str):
                msg = str(msg)
            if isinstance(msg, bytes):
                msg = msg.decode('utf-8')
            tag_text = safe_decode(alarm.get("tag", "UNKNOWN"))
            ts = alarm.get("timestamp", 0)
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"
            line = f"  [{ts_str}] {tag_text}: {msg} (sev={alarm.get('severity', 0)})"
            active.add_line(line)

        sections.append(active)
        print(f"Alarm report generated: {len(alarms)} alarms")
        return sections

    def generate_trend_report(self, trend_data, period_label="Last 24h"):
        """Analyse sensor trends and produce a narrative report."""
        sections = []
        header = ReportSection("Trend Analysis \u2014 " + period_label)
        header.add_line("Site: " + self._site_name)
        sections.append(header)

        trends = ReportSection("Per-Sensor Trends")
        for tag, points in trend_data.items():
            if len(points) < 2:
                continue
            tag_label = safe_decode(tag) if not isinstance(tag, str) else tag
            values = [p[1] for p in points]
            delta = values[-1] - values[0]
            pct = (delta / values[0] * 100.0) if values[0] != 0 else 0.0
            avg = functools.reduce(lambda a, b: a + b, values) / len(values)
            arrow = "\u2191" if delta > 0 else "\u2193" if delta < 0 else "\u2192"
            trends.add_line(f"  {arrow} {tag_label}: {values[0]:.2f} \u2192 {values[-1]:.2f} ({pct:+.1f}%)")
            trends.add_line(f"    Average: {avg:.2f}, Samples: {len(values)}")

        sections.append(trends)
        print(f"Trend report generated for {len(trend_data)} sensors")
        return sections

    def render_report(self, sections, template_name=None):
        """Render a list of ReportSections to a unicode string."""
        if template_name and template_name in self.templates:
            try:
                context = {"sections": sections, "site_name": self._site_name,
                           "report_time": time.strftime("%Y-%m-%d %H:%M:%S")}
                lines = self.templates[template_name].evaluate(context)
                output = "\n".join([safe_decode(l) for l in lines])
                print(f"Report rendered via template '{template_name}'")
                return output
            except ReportError as e:
                print(f"Template render failed, falling back: {e}", file=sys.stderr)

        parts = [self.DEFAULT_TITLE, ""]
        for section in sections:
            parts.append(section.render())
        output = "\n".join(parts)
        print(f"Report rendered ({len(sections)} sections, {len(output)} chars)")
        return output

    def save_report(self, content, filename):
        """Write rendered report content to disk."""
        if not isinstance(content, str):
            raise ReportError("Report content must be a string")
        encoded = safe_encode(content)
        filepath = os.path.join(self._output_dir, filename)
        try:
            with open(filepath, "wb") as fh:
                fh.write(encoded)
            print(f"Report saved to {filepath} ({len(encoded)} bytes)")
        except IOError as e:
            print(f"Failed to save report to {filepath}: {e}", file=sys.stderr)
            raise ReportError(f"Could not write report: {e}")
