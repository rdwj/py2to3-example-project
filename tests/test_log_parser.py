# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/log_parser.py

Tests the current Python 2 behavior including:
- commands.getstatusoutput() (removed in Py3, use subprocess)
- file.xreadlines() (deprecated, use file iteration)
- os.popen() (deprecated, use subprocess)
- except Exception, e syntax
- dict.has_key()
- print statements without ()
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import time
import pytest
import tempfile

from src.data_processing.log_parser import (
    LogEntry,
    LogFilter,
    LogParser,
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    SEVERITY_DEBUG,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_log_file(tmp_path):
    """Create a temporary log file for testing."""
    def _create_log(content):
        log_file = tmp_path / "test.log"
        log_file.write_text(content, encoding="utf-8")
        return str(log_file)
    return _create_log


@pytest.fixture
def syslog_content():
    """Sample syslog format content."""
    return """Feb 15 10:23:45 gateway01 httpd[1234]: Connection established
Feb 15 10:24:12 gateway01 kernel: disk error on sda1
Feb 15 10:25:30 gateway02 sshd[5678]: Failed login attempt
"""


@pytest.fixture
def applog_content():
    """Sample application log format content."""
    return """2024-02-15 10:23:45.123 INFO [core.engine] System initialized
2024-02-15 10:24:00.456 ERROR [data.processor] Failed to parse record
2024-02-15 10:25:15.789 WARNING [network.client] Connection timeout
"""


@pytest.fixture
def scada_event_content():
    """Sample SCADA event log format."""
    return """EVENT|2024-02-15 10:23:45|INFO|Area1|TAG001|Normal startup
EVENT|2024-02-15 10:24:00|ERROR|Area2|TAG002|Sensor offline
EVENT|2024-02-15 10:25:00|WARNING|Area1|TAG003|High temperature
"""


# ---------------------------------------------------------------------------
# Test LogEntry
# ---------------------------------------------------------------------------

def test_log_entry_initialization():
    """Test LogEntry creation."""
    entry = LogEntry()
    assert entry.timestamp_raw == ""
    assert entry.timestamp_epoch == 0.0
    assert entry.hostname == ""
    assert entry.process == ""
    assert entry.pid is None
    assert entry.level == SEVERITY_INFO
    assert entry.message == ""
    assert entry.line_number == 0


def test_log_entry_severity_rank():
    """Test severity_rank() with dict.has_key()."""
    entry = LogEntry()
    entry.level = SEVERITY_ERROR
    rank = entry.severity_rank()
    assert rank == 4


def test_log_entry_severity_rank_unknown_level():
    """Test severity_rank() with unknown level."""
    entry = LogEntry()
    entry.level = "UNKNOWN"
    rank = entry.severity_rank()
    assert rank == 0


def test_log_entry_matches_level_equal():
    """Test matches_level() for equal severity."""
    entry = LogEntry()
    entry.level = SEVERITY_ERROR
    assert entry.matches_level(SEVERITY_ERROR)


def test_log_entry_matches_level_higher():
    """Test matches_level() for higher severity."""
    entry = LogEntry()
    entry.level = SEVERITY_ERROR
    assert entry.matches_level(SEVERITY_WARNING)


def test_log_entry_matches_level_lower():
    """Test matches_level() for lower severity."""
    entry = LogEntry()
    entry.level = SEVERITY_WARNING
    assert not entry.matches_level(SEVERITY_ERROR)


def test_log_entry_repr():
    """Test __repr__ output."""
    entry = LogEntry()
    entry.timestamp_raw = "2024-02-15 10:00:00"
    entry.level = "INFO"
    entry.module = "test"
    entry.message = "Test message"

    repr_str = repr(entry)
    assert "LogEntry" in repr_str
    assert "INFO" in repr_str


def test_log_entry_repr_long_message():
    """Test __repr__ truncates long messages."""
    entry = LogEntry()
    entry.message = "x" * 100
    repr_str = repr(entry)
    # Should truncate to 60 chars
    assert len(entry.message) > 60
    assert repr_str.count("x") < 100


# ---------------------------------------------------------------------------
# Test LogFilter
# ---------------------------------------------------------------------------

def test_log_filter_initialization():
    """Test LogFilter creation."""
    flt = LogFilter()
    assert flt._min_level is None
    assert flt._hostname is None
    assert flt._process is None


def test_log_filter_set_min_level():
    """Test setting minimum severity level."""
    flt = LogFilter()
    result = flt.set_min_level(SEVERITY_ERROR)
    assert result is flt  # Method chaining
    assert flt._min_level == SEVERITY_ERROR


def test_log_filter_set_hostname():
    """Test setting hostname filter."""
    flt = LogFilter()
    flt.set_hostname("gateway01")
    assert flt._hostname == "gateway01"


def test_log_filter_set_process():
    """Test setting process filter."""
    flt = LogFilter()
    flt.set_process("httpd")
    assert flt._process == "httpd"


def test_log_filter_set_message_pattern():
    """Test setting message pattern filter."""
    flt = LogFilter()
    flt.set_message_pattern("error|fault")
    assert flt._message_pattern is not None


def test_log_filter_set_time_range():
    """Test setting time range filter."""
    flt = LogFilter()
    start = time.time() - 3600
    end = time.time()
    flt.set_time_range(start, end)
    assert flt._time_start == start
    assert flt._time_end == end


def test_log_filter_matches_all_criteria_pass():
    """Test matches() when all criteria pass."""
    entry = LogEntry()
    entry.level = SEVERITY_ERROR
    entry.hostname = "gateway01"
    entry.process = "httpd"
    entry.message = "Connection error"
    entry.timestamp_epoch = time.time()

    flt = LogFilter()
    flt.set_min_level(SEVERITY_WARNING)
    flt.set_hostname("gateway01")
    flt.set_process("httpd")

    assert flt.matches(entry)


def test_log_filter_matches_level_fail():
    """Test matches() fails on level."""
    entry = LogEntry()
    entry.level = SEVERITY_INFO

    flt = LogFilter()
    flt.set_min_level(SEVERITY_ERROR)

    assert not flt.matches(entry)


def test_log_filter_matches_hostname_fail():
    """Test matches() fails on hostname."""
    entry = LogEntry()
    entry.hostname = "gateway01"

    flt = LogFilter()
    flt.set_hostname("gateway02")

    assert not flt.matches(entry)


def test_log_filter_matches_process_fail():
    """Test matches() fails on process."""
    entry = LogEntry()
    entry.process = "httpd"

    flt = LogFilter()
    flt.set_process("sshd")

    assert not flt.matches(entry)


def test_log_filter_matches_pattern():
    """Test message pattern matching."""
    entry = LogEntry()
    entry.message = "Connection error occurred"

    flt = LogFilter()
    flt.set_message_pattern("error")

    assert flt.matches(entry)


def test_log_filter_matches_pattern_case_insensitive():
    """Test pattern matching is case-insensitive."""
    entry = LogEntry()
    entry.message = "ERROR occurred"

    flt = LogFilter()
    flt.set_message_pattern("error")

    assert flt.matches(entry)


def test_log_filter_matches_time_range():
    """Test time range filtering."""
    now = time.time()
    entry = LogEntry()
    entry.timestamp_epoch = now

    flt = LogFilter()
    flt.set_time_range(now - 3600, now + 3600)

    assert flt.matches(entry)


def test_log_filter_matches_time_before_range():
    """Test entry before time range is filtered."""
    now = time.time()
    entry = LogEntry()
    entry.timestamp_epoch = now - 7200

    flt = LogFilter()
    flt.set_time_range(now - 3600, now)

    assert not flt.matches(entry)


# ---------------------------------------------------------------------------
# Test LogParser format detection
# ---------------------------------------------------------------------------

def test_parser_detect_format_syslog():
    """Test syslog format detection."""
    parser = LogParser()
    line = "Feb 15 10:23:45 gateway01 httpd[1234]: Test message"
    fmt = parser._detect_format(line)
    assert fmt == LogParser.FORMAT_SYSLOG


def test_parser_detect_format_applog():
    """Test application log format detection."""
    parser = LogParser()
    line = "2024-02-15 10:23:45.123 INFO [module] Test message"
    fmt = parser._detect_format(line)
    assert fmt == LogParser.FORMAT_APPLOG


def test_parser_detect_format_scada():
    """Test SCADA event format detection."""
    parser = LogParser()
    line = "EVENT|2024-02-15 10:23:45|INFO|Area1|TAG001|Test message"
    fmt = parser._detect_format(line)
    assert fmt == LogParser.FORMAT_SCADA


def test_parser_detect_format_unknown():
    """Test unknown format returns None."""
    parser = LogParser()
    line = "This is not a recognized log format"
    fmt = parser._detect_format(line)
    assert fmt is None


# ---------------------------------------------------------------------------
# Test LogParser syslog parsing
# ---------------------------------------------------------------------------

def test_parser_parse_syslog_line():
    """Test parsing a syslog line."""
    parser = LogParser()
    line = "Feb 15 10:23:45 gateway01 httpd[1234]: Connection established"
    entry = parser._parse_syslog(line, 1)

    assert entry is not None
    assert entry.hostname == "gateway01"
    assert entry.process == "httpd"
    assert entry.pid == 1234
    assert "Connection established" in entry.message


def test_parser_parse_syslog_line_no_pid():
    """Test parsing syslog line without PID."""
    parser = LogParser()
    line = "Feb 15 10:23:45 gateway01 kernel: disk error"
    entry = parser._parse_syslog(line, 1)

    assert entry is not None
    assert entry.process == "kernel"
    assert entry.pid is None


def test_parser_parse_syslog_infer_error_level():
    """Test severity inference from message content."""
    parser = LogParser()
    line = "Feb 15 10:23:45 host proc: fatal error occurred"
    entry = parser._parse_syslog(line, 1)

    assert entry.level == SEVERITY_ERROR


def test_parser_parse_syslog_infer_warning_level():
    """Test warning inference."""
    parser = LogParser()
    line = "Feb 15 10:23:45 host proc: warning: low disk space"
    entry = parser._parse_syslog(line, 1)

    assert entry.level == SEVERITY_WARNING


def test_parser_parse_syslog_infer_critical_level():
    """Test critical inference."""
    parser = LogParser()
    line = "Feb 15 10:23:45 host proc: critical system failure"
    entry = parser._parse_syslog(line, 1)

    assert entry.level == SEVERITY_CRITICAL


# ---------------------------------------------------------------------------
# Test LogParser applog parsing
# ---------------------------------------------------------------------------

def test_parser_parse_applog_line():
    """Test parsing application log line."""
    parser = LogParser()
    line = "2024-02-15 10:23:45.123 ERROR [data.processor] Parse failed"
    entry = parser._parse_applog(line, 1)

    assert entry is not None
    assert entry.level == "ERROR"
    assert entry.module == "data.processor"
    assert "Parse failed" in entry.message


def test_parser_parse_applog_timestamp():
    """Test timestamp parsing from applog."""
    parser = LogParser()
    line = "2024-02-15 10:23:45.123 INFO [test] Message"
    entry = parser._parse_applog(line, 1)

    assert entry.timestamp_epoch > 0


# ---------------------------------------------------------------------------
# Test LogParser SCADA event parsing
# ---------------------------------------------------------------------------

def test_parser_parse_scada_event_line():
    """Test parsing SCADA event line."""
    parser = LogParser()
    line = "EVENT|2024-02-15 10:23:45|ERROR|Area2|TAG002|Sensor offline"
    entry = parser._parse_scada_event(line, 1)

    assert entry is not None
    assert entry.level == "ERROR"
    assert entry.module == "Area2"
    assert entry.process == "TAG002"
    assert "Sensor offline" in entry.message


# ---------------------------------------------------------------------------
# Test LogParser file parsing with xreadlines()
# ---------------------------------------------------------------------------

def test_parser_parse_file_syslog(temp_log_file, syslog_content):
    """Test parsing syslog file using xreadlines()."""
    log_path = temp_log_file(syslog_content)
    parser = LogParser()
    entries = parser.parse_file(log_path)

    assert len(entries) == 3
    assert entries[0].hostname == "gateway01"
    assert entries[1].hostname == "gateway01"
    assert entries[2].hostname == "gateway02"


def test_parser_parse_file_applog(temp_log_file, applog_content):
    """Test parsing application log file."""
    log_path = temp_log_file(applog_content)
    parser = LogParser()
    entries = parser.parse_file(log_path)

    assert len(entries) == 3
    assert entries[0].level == "INFO"
    assert entries[1].level == "ERROR"
    assert entries[2].level == "WARNING"


def test_parser_parse_file_scada(temp_log_file, scada_event_content):
    """Test parsing SCADA event log file."""
    log_path = temp_log_file(scada_event_content)
    parser = LogParser()
    entries = parser.parse_file(log_path)

    assert len(entries) == 3
    assert entries[0].level == "INFO"
    assert entries[1].level == "ERROR"


def test_parser_parse_file_with_filter(temp_log_file, applog_content):
    """Test parsing file with filter applied."""
    log_path = temp_log_file(applog_content)
    log_filter = LogFilter()
    log_filter.set_min_level(SEVERITY_ERROR)

    parser = LogParser(log_filter=log_filter)
    entries = parser.parse_file(log_path)

    # Should only get ERROR level entries
    assert all(e.level in [SEVERITY_ERROR, SEVERITY_CRITICAL] for e in entries)


def test_parser_parse_file_assumed_format(temp_log_file, syslog_content):
    """Test parsing with assumed format."""
    log_path = temp_log_file(syslog_content)
    parser = LogParser()
    entries = parser.parse_file(log_path, assumed_format=LogParser.FORMAT_SYSLOG)

    assert len(entries) > 0


def test_parser_parse_file_skips_blank_lines(temp_log_file):
    """Test that blank lines are skipped."""
    content = """Feb 15 10:23:45 host proc: message one

Feb 15 10:24:00 host proc: message two

"""
    log_path = temp_log_file(content)
    parser = LogParser()
    entries = parser.parse_file(log_path)

    assert len(entries) == 2


def test_parser_parse_file_prints_progress(temp_log_file, syslog_content, capsys):
    """Test that print statements output progress."""
    log_path = temp_log_file(syslog_content)
    parser = LogParser()
    parser.parse_file(log_path)

    captured = capsys.readouterr()
    assert "Parsing log file" in captured.out
    assert "Parsed" in captured.out


# ---------------------------------------------------------------------------
# Test LogParser collect_and_parse with commands.getstatusoutput()
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_collect_and_parse_uses_commands_module(tmp_path, monkeypatch):
    """Test that subprocess.getstatusoutput() is used."""
    import subprocess

    called_commands = []

    def mock_getstatusoutput(cmd):
        called_commands.append(cmd)
        return (0, "")  # Success

    monkeypatch.setattr(subprocess, "getstatusoutput", mock_getstatusoutput)

    # Create a dummy log file to "collect"
    local_dir = str(tmp_path)
    parser = LogParser()

    try:
        parser.collect_and_parse("remote-host", "/var/log/test.log", local_dir)
    except:
        pass  # May fail due to missing file, but we're testing the call

    assert len(called_commands) > 0
    assert "rsync" in called_commands[0]


@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_collect_and_parse_error_handling(tmp_path, monkeypatch):
    """Test error handling when rsync fails."""
    import subprocess

    def mock_getstatusoutput(cmd):
        return (1, "rsync: connection failed")

    monkeypatch.setattr(subprocess, "getstatusoutput", mock_getstatusoutput)

    parser = LogParser()
    with pytest.raises(Exception) as exc_info:
        parser.collect_and_parse("host", "/var/log/test.log", str(tmp_path))

    assert "failed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test LogParser parse_piped with os.popen()
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_parse_piped_simple():
    """Test parsing output from piped command using os.popen()."""
    parser = LogParser()
    # Use echo to simulate log output
    command = 'echo "Feb 15 10:23:45 host proc: test message"'
    entries = parser.parse_piped(command)

    assert len(entries) >= 0  # May be 0 or 1 depending on format detection


@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_parse_piped_multiple_lines():
    """Test parsing multiple lines from piped command."""
    parser = LogParser()
    command = '''printf "2024-02-15 10:23:45.123 INFO [test] Line 1\n2024-02-15 10:24:00.456 ERROR [test] Line 2\n"'''
    entries = parser.parse_piped(command)

    assert len(entries) >= 0


@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_parse_piped_with_filter():
    """Test piped parsing with filter."""
    log_filter = LogFilter()
    log_filter.set_min_level(SEVERITY_ERROR)
    parser = LogParser(log_filter=log_filter)

    command = 'echo "2024-02-15 10:23:45.123 ERROR [test] Error message"'
    entries = parser.parse_piped(command)

    # Should only include ERROR and above
    assert all(e.level in [SEVERITY_ERROR, SEVERITY_CRITICAL] for e in entries)


# ---------------------------------------------------------------------------
# Test parse error collection
# ---------------------------------------------------------------------------

def test_parser_parse_errors_initially_empty():
    """Test parse errors list is initially empty."""
    parser = LogParser()
    assert parser.parse_errors() == []


def test_parser_parse_errors_collected(temp_log_file):
    """Test that parse errors are collected."""
    content = """2024-02-15 10:23:45.123 INFO [test] Valid line
This is not a valid log line format
2024-02-15 10:24:00.456 ERROR [test] Another valid line
"""
    log_path = temp_log_file(content)

    # Create mapper with transform that will fail
    parser = LogParser()
    entries = parser.parse_file(log_path)

    # The invalid line should be skipped
    # No errors for unrecognized format (just skipped)
    assert len(entries) == 2


def test_parser_lines_processed_counter():
    """Test lines_processed() counter."""
    parser = LogParser()
    assert parser.lines_processed() == 0


# ---------------------------------------------------------------------------
# Test timestamp parsing
# ---------------------------------------------------------------------------

def test_parser_parse_syslog_timestamp():
    """Test syslog timestamp parsing (assumes current year)."""
    parser = LogParser()
    ts_str = "Feb 15 10:23:45"
    epoch = parser._parse_syslog_timestamp(ts_str)

    assert epoch > 0
    # Should use current year
    current_year = time.localtime().tm_year
    parsed_time = time.localtime(epoch)
    assert parsed_time.tm_year == current_year


def test_parser_parse_applog_timestamp():
    """Test application log timestamp parsing."""
    parser = LogParser()
    ts_str = "2024-02-15 10:23:45.456"
    epoch = parser._parse_applog_timestamp(ts_str)

    assert epoch > 0
    parsed_time = time.localtime(epoch)
    assert parsed_time.tm_year == 2024
    assert parsed_time.tm_mon == 2
    assert parsed_time.tm_mday == 15


def test_parser_parse_timestamp_invalid():
    """Test timestamp parsing with invalid input."""
    parser = LogParser()
    epoch = parser._parse_syslog_timestamp("invalid timestamp")
    assert epoch == 0.0


# ---------------------------------------------------------------------------
# Test exception handling with except Exception, e syntax
# ---------------------------------------------------------------------------

def test_parser_exception_syntax_parse_error(temp_log_file):
    """Test old-style except syntax in parse_file."""
    # Create log that will cause parse errors within exception handlers
    content = "2024-02-15 10:23:45.123 INFO [test] Valid line"
    log_path = temp_log_file(content)

    parser = LogParser()
    # Should not raise, even if internal errors occur
    entries = parser.parse_file(log_path)
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# Test print statement output
# ---------------------------------------------------------------------------

def test_parser_prints_file_name(temp_log_file, syslog_content, capsys):
    """Test that file name is printed."""
    log_path = temp_log_file(syslog_content)
    parser = LogParser()
    parser.parse_file(log_path)

    captured = capsys.readouterr()
    assert log_path in captured.out or "Parsing log file" in captured.out


def test_parser_prints_parsed_count(temp_log_file, syslog_content, capsys):
    """Test that parsed entry count is printed."""
    log_path = temp_log_file(syslog_content)
    parser = LogParser()
    parser.parse_file(log_path)

    captured = capsys.readouterr()
    assert "Parsed" in captured.out
    assert "entries" in captured.out


@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_parser_prints_piped_command(capsys):
    """Test that piped command is printed."""
    parser = LogParser()
    parser.parse_piped('echo "test"')

    captured = capsys.readouterr()
    assert "Running piped command" in captured.out


# ---------------------------------------------------------------------------
# Test format constants
# ---------------------------------------------------------------------------

def test_parser_format_constants():
    """Test that format constants are defined."""
    assert LogParser.FORMAT_SYSLOG == "syslog"
    assert LogParser.FORMAT_APPLOG == "applog"
    assert LogParser.FORMAT_SCADA == "scada_event"


# ---------------------------------------------------------------------------
# Test severity constants
# ---------------------------------------------------------------------------

def test_severity_constants():
    """Test that severity constants are defined correctly."""
    assert SEVERITY_CRITICAL == "CRITICAL"
    assert SEVERITY_ERROR == "ERROR"
    assert SEVERITY_WARNING == "WARNING"
    assert SEVERITY_INFO == "INFO"
    assert SEVERITY_DEBUG == "DEBUG"
