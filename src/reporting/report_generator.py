# -*- coding: utf-8 -*-
"""
Report generation engine for the Legacy Industrial Data Platform.

Produces daily summaries, alarm reports, and trend analysis documents
from sensor data.  Report templates are evaluated dynamically via
``exec`` so that plant engineers can customise output without modifying
Python code -- a decision made in 2009 that nobody has revisited.
"""

import sys
import time
import os

from core.types import DataPoint, is_string
from core.string_helpers import safe_decode, safe_encode
from core.exceptions import PlatformError


class ReportError(PlatformError):
    """Raised when report generation or template evaluation fails."""
    pass


class ReportSection(object):
    """A single section of a generated report (header, data table, etc.).
    Carries a unicode title and a list of content lines."""

    def __init__(self, title, content_lines=None):
        if isinstance(title, basestring):
            self.title = safe_decode(title) if not isinstance(title, unicode) else title
        else:
            self.title = unicode(title)
        self.content_lines = content_lines or []
        self.timestamp = time.time()

    def add_line(self, line):
        if isinstance(line, basestring):
            self.content_lines.append(safe_decode(line))
        else:
            self.content_lines.append(unicode(line))

    def render(self):
        header = u"=== " + self.title + u" ==="
        body = u"\n".join(self.content_lines)
        return header + u"\n" + body + u"\n"


class ReportTemplate(object):
    """Wraps a template code string that gets ``exec``-ed at render time.

    Template code writes into a ``lines`` list in the exec namespace.
    Templates live in /opt/platform/templates/ and are version-controlled
    separately from this codebase.
    """

    def __init__(self, name, code_string, description=u""):
        self.name = name
        self.code_string = code_string
        self.description = description

    def evaluate(self, context):
        """Execute the template code with *context* as the namespace."""
        namespace = {"lines": [], "time": time, "unicode": unicode}
        namespace.update(context)
        try:
            exec self.code_string in namespace
        except SyntaxError, e:
            print >>sys.stderr, "Template syntax error in '%s': %s" % (self.name, e)
            raise ReportError("Bad template syntax: %s" % e)
        except Exception, e:
            print >>sys.stderr, "Template execution error in '%s': %s" % (self.name, e)
            raise ReportError("Template failed: %s" % e)
        return namespace["lines"]


class ReportGenerator(object):
    """Generates reports from sensor data and alarm history.

    Supports daily summaries, alarm digests, and trend analysis.
    """

    DEFAULT_TITLE = u"Industrial Data Platform \u2014 Report"

    def __init__(self, config=None):
        self.config = config or {}
        self.templates = {}
        self._output_dir = self.config.get("output_dir", "/var/platform/reports")
        self._site_name = self.config.get("site_name", u"Plant A")

    def register_template(self, template):
        if not isinstance(template, ReportTemplate):
            raise ReportError("Expected ReportTemplate, got %s" % type(template).__name__)
        self.templates[template.name] = template

    def generate_daily_summary(self, sensor_data, report_date=None):
        """Build a daily summary from a dict of sensor_tag -> readings."""
        if report_date is None:
            report_date = time.strftime("%Y-%m-%d")

        sections = []
        header = ReportSection(u"Daily Summary \u2014 " + unicode(report_date))
        header.add_line(u"Site: " + self._site_name)
        header.add_line(u"Generated: " + unicode(time.strftime("%Y-%m-%d %H:%M:%S")))
        header.add_line(u"Total sensors reporting: %d" % len(sensor_data))
        sections.append(header)

        stats = ReportSection(u"Sensor Statistics")
        for tag, readings in sensor_data.iteritems():
            values = []
            for r in readings:
                if isinstance(r, DataPoint):
                    values.append(r.value)
                elif isinstance(r, (int, float, long)):
                    values.append(r)
            if not values:
                continue

            total = reduce(lambda a, b: a + b, values, 0.0)
            avg = total / len(values)
            min_val = reduce(lambda a, b: a if a < b else b, values)
            max_val = reduce(lambda a, b: a if a > b else b, values)

            tag_label = safe_decode(tag) if not isinstance(tag, unicode) else tag
            line = u"  " + tag_label + u": "
            line = line + u"avg=%.2f, min=%.2f, max=%.2f, n=%d" % (avg, min_val, max_val, len(values))
            stats.add_line(line)

        sections.append(stats)
        print "Daily summary generated for %s (%d sensors)" % (report_date, len(sensor_data))
        return sections

    def generate_alarm_report(self, alarms, severity_filter=None):
        """Build a report of active alarms."""
        sections = []
        title_sec = ReportSection(u"Alarm Report")
        title_sec.add_line(u"Site: " + self._site_name)
        title_sec.add_line(u"Report time: " + unicode(time.strftime("%Y-%m-%d %H:%M:%S")))
        sections.append(title_sec)

        if severity_filter is not None:
            alarms = [a for a in alarms if a.get("severity", 0) >= severity_filter]

        active = ReportSection(u"Active Alarms (%d)" % len(alarms))
        for alarm in alarms:
            msg = alarm.get("message", "")
            if not isinstance(msg, basestring):
                msg = str(msg)
            msg_text = unicode(msg, 'utf-8') if isinstance(msg, str) else msg
            tag_text = safe_decode(alarm.get("tag", "UNKNOWN"))
            ts = alarm.get("timestamp", 0)
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else u"--:--:--"
            line = u"  [%s] %s: %s (sev=%d)" % (ts_str, tag_text, msg_text, alarm.get("severity", 0))
            active.add_line(line)

        sections.append(active)
        print "Alarm report generated: %d alarms" % len(alarms)
        return sections

    def generate_trend_report(self, trend_data, period_label=u"Last 24h"):
        """Analyse sensor trends and produce a narrative report."""
        sections = []
        header = ReportSection(u"Trend Analysis \u2014 " + period_label)
        header.add_line(u"Site: " + self._site_name)
        sections.append(header)

        trends = ReportSection(u"Per-Sensor Trends")
        for tag, points in trend_data.iteritems():
            if len(points) < 2:
                continue
            tag_label = safe_decode(tag) if not isinstance(tag, unicode) else tag
            values = [p[1] for p in points]
            delta = values[-1] - values[0]
            pct = (delta / values[0] * 100.0) if values[0] != 0 else 0.0
            avg = reduce(lambda a, b: a + b, values) / len(values)
            arrow = u"\u2191" if delta > 0 else u"\u2193" if delta < 0 else u"\u2192"
            trends.add_line(u"  %s %s: %.2f \u2192 %.2f (%+.1f%%)" % (
                arrow, tag_label, values[0], values[-1], pct))
            trends.add_line(u"    Average: %.2f, Samples: %d" % (avg, len(values)))

        sections.append(trends)
        print "Trend report generated for %d sensors" % len(trend_data)
        return sections

    def render_report(self, sections, template_name=None):
        """Render a list of ReportSections to a unicode string."""
        if template_name and template_name in self.templates:
            try:
                context = {"sections": sections, "site_name": self._site_name,
                           "report_time": time.strftime("%Y-%m-%d %H:%M:%S")}
                lines = self.templates[template_name].evaluate(context)
                output = u"\n".join([safe_decode(l) for l in lines])
                print "Report rendered via template '%s'" % template_name
                return output
            except ReportError, e:
                print >>sys.stderr, "Template render failed, falling back: %s" % e

        parts = [self.DEFAULT_TITLE, u""]
        for section in sections:
            parts.append(section.render())
        output = u"\n".join(parts)
        print "Report rendered (%d sections, %d chars)" % (len(sections), len(output))
        return output

    def save_report(self, content, filename):
        """Write rendered report content to disk."""
        if not isinstance(content, basestring):
            raise ReportError("Report content must be a string")
        encoded = safe_encode(content) if isinstance(content, unicode) else content
        filepath = os.path.join(self._output_dir, filename)
        try:
            fh = open(filepath, "wb")
            try:
                fh.write(encoded)
            finally:
                fh.close()
            print "Report saved to %s (%d bytes)" % (filepath, len(encoded))
        except IOError, e:
            print >>sys.stderr, "Failed to save report to %s: %s" % (filepath, e)
            raise ReportError("Could not write report: %s" % e)
