# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/log_parser.py

Captures pre-migration behavior of:
- LogEntry with dict.has_key() for severity lookup
- LogFilter criteria-based filtering
- LogParser format detection and line parsing
- Py2-specific: commands module, os.popen, .xreadlines(),
  dict.has_key(), except comma syntax
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.data_processing.log_parser import (
    LogEntry, LogFilter, LogParser,
    SEVERITY_CRITICAL, SEVERITY_ERROR, SEVERITY_WARNING,
    SEVERITY_INFO, SEVERITY_DEBUG,
)


class TestLogEntry:
    """Characterize log entry data holder."""

    def test_construction(self):
        """Captures: default field values."""
        entry = LogEntry()
        assert entry.level == SEVERITY_INFO
        assert entry.message == ""
        assert entry.pid is None

    @pytest.mark.py2_behavior
    def test_severity_rank_uses_has_key(self):
        """Captures: dict.has_key() for severity lookup. Removed in Py3."""
        entry = LogEntry()
        entry.level = SEVERITY_ERROR
        assert entry.severity_rank() == 4

    def test_severity_rank_unknown(self):
        """Captures: unknown level returns 0."""
        entry = LogEntry()
        entry.level = "UNKNOWN"
        assert entry.severity_rank() == 0

    def test_matches_level(self):
        """Captures: severity comparison."""
        entry = LogEntry()
        entry.level = SEVERITY_ERROR
        assert entry.matches_level(SEVERITY_WARNING) is True
        assert entry.matches_level(SEVERITY_CRITICAL) is False


class TestLogFilter:
    """Characterize log entry filtering."""

    def test_filter_by_level(self):
        """Captures: min_level filter."""
        f = LogFilter().set_min_level(SEVERITY_WARNING)
        info_entry = LogEntry()
        info_entry.level = SEVERITY_INFO
        warn_entry = LogEntry()
        warn_entry.level = SEVERITY_WARNING
        assert f.matches(info_entry) is False
        assert f.matches(warn_entry) is True

    def test_filter_by_hostname(self):
        """Captures: hostname filter."""
        f = LogFilter().set_hostname("gw01")
        entry = LogEntry()
        entry.hostname = "gw01"
        assert f.matches(entry) is True
        entry.hostname = "gw02"
        assert f.matches(entry) is False

    def test_filter_by_message_pattern(self):
        """Captures: regex message pattern filter."""
        f = LogFilter().set_message_pattern("error|fail")
        entry = LogEntry()
        entry.message = "Connection failed"
        assert f.matches(entry) is True
        entry.message = "All good"
        assert f.matches(entry) is False

    def test_filter_chaining(self):
        """Captures: multiple filters combined (all must match)."""
        f = (LogFilter()
             .set_min_level(SEVERITY_ERROR)
             .set_hostname("gw01"))
        entry = LogEntry()
        entry.level = SEVERITY_ERROR
        entry.hostname = "gw01"
        assert f.matches(entry) is True
        entry.hostname = "gw02"
        assert f.matches(entry) is False


class TestLogParser:
    """Characterize log file parsing."""

    def test_parse_syslog_line(self, tmp_path):
        """Captures: syslog format detection and parsing."""
        log_file = tmp_path / "test.log"
        log_file.write_text("Feb 12 14:23:01 gw01 modbus[1234]: Connection established\n")
        parser = LogParser()
        entries = parser.parse_file(str(log_file))
        assert len(entries) == 1
        assert entries[0].hostname == "gw01"
        assert entries[0].process == "modbus"
        assert entries[0].pid == 1234
        assert "Connection established" in entries[0].message

    def test_parse_applog_line(self, tmp_path):
        """Captures: application log format detection."""
        log_file = tmp_path / "app.log"
        log_file.write_text("2024-01-15 14:23:01.456 ERROR [sensor] Reading failed\n")
        parser = LogParser()
        entries = parser.parse_file(str(log_file))
        assert len(entries) == 1
        assert entries[0].level == SEVERITY_ERROR
        assert entries[0].module == "sensor"

    def test_parse_scada_event(self, tmp_path):
        """Captures: SCADA event log format."""
        log_file = tmp_path / "scada.log"
        log_file.write_text("EVENT|2024-01-15 10:00:00.000|WARNING|Area1|TEMP-001|High temperature\n")
        parser = LogParser()
        entries = parser.parse_file(str(log_file))
        assert len(entries) == 1
        assert entries[0].level == SEVERITY_WARNING

    def test_parse_with_filter(self, tmp_path):
        """Captures: parser applies filter during parsing."""
        log_file = tmp_path / "filtered.log"
        log_file.write_text(
            "2024-01-15 14:23:01.000 ERROR [sensor] Bad reading\n"
            "2024-01-15 14:23:02.000 INFO [sensor] All good\n"
        )
        f = LogFilter().set_min_level(SEVERITY_ERROR)
        parser = LogParser(log_filter=f)
        entries = parser.parse_file(str(log_file))
        assert len(entries) == 1
        assert entries[0].level == SEVERITY_ERROR

    def test_parse_empty_file(self, tmp_path):
        """Captures: empty file produces no entries."""
        log_file = tmp_path / "empty.log"
        log_file.write_text("")
        parser = LogParser()
        entries = parser.parse_file(str(log_file))
        assert entries == []

    def test_syslog_level_inference(self, tmp_path):
        """Captures: level inferred from message content heuristics."""
        log_file = tmp_path / "levels.log"
        log_file.write_text(
            "Feb 12 10:00:00 gw01 app: Connection error detected\n"
            "Feb 12 10:00:01 gw01 app: Normal operation\n"
        )
        parser = LogParser()
        entries = parser.parse_file(str(log_file))
        assert entries[0].level == SEVERITY_ERROR
        assert entries[1].level == SEVERITY_INFO

    def test_lines_processed_counter(self, tmp_path):
        """Captures: lines_processed tracks total lines read."""
        log_file = tmp_path / "count.log"
        log_file.write_text("Feb 12 10:00:00 gw01 app: msg1\nFeb 12 10:00:01 gw01 app: msg2\n")
        parser = LogParser()
        parser.parse_file(str(log_file))
        assert parser.lines_processed() == 2
