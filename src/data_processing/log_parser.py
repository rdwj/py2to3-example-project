# -*- coding: utf-8 -*-
"""
Log file parser for industrial system logs.

Parses structured and semi-structured log files from multiple sources:
syslog output from the gateway servers, application logs from the
historian, and event logs from the SCADA system.  Logs are collected
from remote hosts via SSH/rsync and stored in /var/log/platform/ for
centralised analysis.

Some logs are very large (multi-GB syslog archives from busy gateways),
so the parser uses lazy iteration and subprocess-based filtering to
avoid loading entire files into memory.
"""


import os
import re
import time
import subprocess

from src.core.exceptions import ParseError, DataError
from src.core.config_loader import load_platform_config


# ---------------------------------------------------------------------------
# Log format patterns
# ---------------------------------------------------------------------------

# Standard syslog format: "Mon DD HH:MM:SS hostname process[pid]: message"
_SYSLOG_PATTERN = re.compile(
    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"  # timestamp
    r"(\S+)\s+"                                       # hostname
    r"(\S+?)(?:\[(\d+)\])?:\s+"                       # process[pid]
    r"(.*)$"                                           # message
)

# Application log: "YYYY-MM-DD HH:MM:SS.mmm LEVEL [module] message"
_APPLOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+"  # timestamp
    r"(\w+)\s+"                                                # level
    r"\[([^\]]+)\]\s+"                                         # module
    r"(.*)$"                                                   # message
)

# SCADA event log: "EVENT|timestamp|severity|area|point|description"
_SCADA_EVENT_PATTERN = re.compile(
    r"^EVENT\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|(.*)$"
)

# Severity levels in descending order of importance
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"
SEVERITY_DEBUG = "DEBUG"

_SEVERITY_RANK = {
    SEVERITY_CRITICAL: 5,
    SEVERITY_ERROR: 4,
    SEVERITY_WARNING: 3,
    SEVERITY_INFO: 2,
    SEVERITY_DEBUG: 1,
}


# ---------------------------------------------------------------------------
# LogEntry -- a single parsed log line
# ---------------------------------------------------------------------------

class LogEntry:
    """A single parsed log entry with structured fields."""

    __slots__ = (
        "timestamp_raw", "timestamp_epoch", "hostname", "process",
        "pid", "level", "module", "message", "source_format", "line_number",
    )

    def __init__(self):
        self.timestamp_raw = ""
        self.timestamp_epoch = 0.0
        self.hostname = ""
        self.process = ""
        self.pid = None
        self.level = SEVERITY_INFO
        self.module = ""
        self.message = ""
        self.source_format = ""
        self.line_number = 0

    def severity_rank(self):
        if self.level in _SEVERITY_RANK:
            return _SEVERITY_RANK[self.level]
        return 0

    def matches_level(self, min_level):
        """Return True if this entry's severity meets or exceeds *min_level*."""
        min_rank = _SEVERITY_RANK.get(min_level, 0)
        return self.severity_rank() >= min_rank

    def __repr__(self):
        return "LogEntry(%s %s [%s] %s)" % (
            self.timestamp_raw, self.level, self.module,
            self.message[:60] if len(self.message) > 60 else self.message,
        )


# ---------------------------------------------------------------------------
# LogFilter -- criteria-based log entry filtering
# ---------------------------------------------------------------------------

class LogFilter:
    """Filter log entries by severity, hostname, process, time range,
    and message content patterns."""

    def __init__(self):
        self._min_level = None
        self._hostname = None
        self._process = None
        self._message_pattern = None
        self._time_start = None
        self._time_end = None

    def set_min_level(self, level):
        self._min_level = level
        return self

    def set_hostname(self, hostname):
        self._hostname = hostname
        return self

    def set_process(self, process):
        self._process = process
        return self

    def set_message_pattern(self, pattern):
        self._message_pattern = re.compile(pattern, re.IGNORECASE)
        return self

    def set_time_range(self, start_epoch, end_epoch):
        self._time_start = start_epoch
        self._time_end = end_epoch
        return self

    def matches(self, entry):
        """Return True if *entry* passes all active filter criteria."""
        if self._min_level is not None:
            if not entry.matches_level(self._min_level):
                return False

        if self._hostname is not None:
            if entry.hostname != self._hostname:
                return False

        if self._process is not None:
            if entry.process != self._process:
                return False

        if self._message_pattern is not None:
            if not self._message_pattern.search(entry.message):
                return False

        if self._time_start is not None:
            if entry.timestamp_epoch < self._time_start:
                return False

        if self._time_end is not None:
            if entry.timestamp_epoch > self._time_end:
                return False

        return True


# ---------------------------------------------------------------------------
# LogParser -- the main parsing engine
# ---------------------------------------------------------------------------

class LogParser:
    """Parse log files from multiple sources into structured LogEntry objects.

    Supports syslog, application log, and SCADA event log formats.
    Automatically detects the format from the first non-blank line.
    """

    FORMAT_SYSLOG = "syslog"
    FORMAT_APPLOG = "applog"
    FORMAT_SCADA = "scada_event"

    def __init__(self, log_filter=None):
        self._filter = log_filter
        self._config = load_platform_config()
        self._parse_errors = []
        self._lines_processed = 0

    def parse_file(self, file_path, assumed_format=None):
        """Parse a log file and return matching entries.

        Iterates the file object directly for memory-efficient processing
        of very large log files.
        """
        print("Parsing log file: %s" % file_path)
        start_time = time.time()
        entries = []

        f = open(file_path, "r")
        try:
            line_num = 0
            detected_format = assumed_format

            for line in f:
                line_num += 1
                self._lines_processed += 1
                line = line.rstrip("\n\r")

                if not line.strip():
                    continue

                # Auto-detect format from the first non-blank line
                if detected_format is None:
                    detected_format = self._detect_format(line)
                    if detected_format is None:
                        print("WARNING: Could not detect log format from line %d" % line_num)
                        continue

                try:
                    entry = self._parse_line(line, line_num, detected_format)
                    if entry is not None:
                        if self._filter is None or self._filter.matches(entry):
                            entries.append(entry)
                except Exception as e:
                    self._parse_errors.append(
                        "Line %d: %s (content: %s)" % (
                            line_num, str(e),
                            line[:100] if len(line) > 100 else line,
                        )
                    )
        finally:
            f.close()

        elapsed = time.time() - start_time
        print("Parsed %d entries from %d lines in %.2f seconds" % (
            len(entries), line_num, elapsed,
        ))
        return entries

    def collect_and_parse(self, remote_host, remote_path, local_dir):
        """Collect a log file from a remote host and parse it.

        Uses ``subprocess.getstatusoutput()`` to run rsync for file
        transfer.
        """
        local_path = os.path.join(local_dir, os.path.basename(remote_path))
        rsync_cmd = "rsync -az %s:%s %s" % (remote_host, remote_path, local_path)

        print("Collecting log from %s:%s" % (remote_host, remote_path))
        status, output = subprocess.getstatusoutput(rsync_cmd)

        if status != 0:
            raise DataError(
                "Log collection failed (status %d): %s" % (status, output)
            )

        print("Collected %s, parsing..." % local_path)
        return self.parse_file(local_path)

    def parse_piped(self, command):
        """Parse log output from a piped command using subprocess.

        Used for real-time log tailing and filtered collection, e.g.:
            parser.parse_piped("ssh gw01 'tail -10000 /var/log/syslog'")
        """
        print("Running piped command: %s" % command)
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        entries = []
        line_num = 0
        detected_format = None

        try:
            for line in proc.stdout:
                line_num += 1
                self._lines_processed += 1
                line = line.rstrip("\n\r")

                if not line.strip():
                    continue

                if detected_format is None:
                    detected_format = self._detect_format(line)
                    if detected_format is None:
                        continue

                try:
                    entry = self._parse_line(line, line_num, detected_format)
                    if entry is not None:
                        if self._filter is None or self._filter.matches(entry):
                            entries.append(entry)
                except Exception as e:
                    self._parse_errors.append("Piped line %d: %s" % (line_num, str(e)))
        finally:
            proc.wait()

        print("Parsed %d entries from piped command" % len(entries))
        return entries

    # ---------------------------------------------------------------
    # Format detection
    # ---------------------------------------------------------------

    def _detect_format(self, line):
        """Detect the log format from a sample line."""
        if _SYSLOG_PATTERN.match(line):
            return self.FORMAT_SYSLOG
        if _APPLOG_PATTERN.match(line):
            return self.FORMAT_APPLOG
        if _SCADA_EVENT_PATTERN.match(line):
            return self.FORMAT_SCADA
        return None

    # ---------------------------------------------------------------
    # Line parsing
    # ---------------------------------------------------------------

    def _parse_line(self, line, line_num, fmt):
        """Parse a single log line according to the detected format."""
        if fmt == self.FORMAT_SYSLOG:
            return self._parse_syslog(line, line_num)
        elif fmt == self.FORMAT_APPLOG:
            return self._parse_applog(line, line_num)
        elif fmt == self.FORMAT_SCADA:
            return self._parse_scada_event(line, line_num)
        else:
            raise ParseError("Unknown log format: %s" % fmt)

    def _parse_syslog(self, line, line_num):
        """Parse a syslog-format line."""
        match = _SYSLOG_PATTERN.match(line)
        if not match:
            return None

        entry = LogEntry()
        entry.line_number = line_num
        entry.source_format = self.FORMAT_SYSLOG
        entry.timestamp_raw = match.group(1)
        entry.hostname = match.group(2)
        entry.process = match.group(3)
        entry.pid = int(match.group(4)) if match.group(4) else None
        entry.message = match.group(5)
        entry.level = self._infer_syslog_level(entry.message)
        entry.timestamp_epoch = self._parse_syslog_timestamp(entry.timestamp_raw)
        return entry

    def _parse_applog(self, line, line_num):
        """Parse an application-log-format line."""
        match = _APPLOG_PATTERN.match(line)
        if not match:
            return None

        entry = LogEntry()
        entry.line_number = line_num
        entry.source_format = self.FORMAT_APPLOG
        entry.timestamp_raw = match.group(1)
        entry.level = match.group(2).upper()
        entry.module = match.group(3)
        entry.message = match.group(4)
        entry.timestamp_epoch = self._parse_applog_timestamp(entry.timestamp_raw)
        return entry

    def _parse_scada_event(self, line, line_num):
        """Parse a SCADA event log line."""
        match = _SCADA_EVENT_PATTERN.match(line)
        if not match:
            return None

        entry = LogEntry()
        entry.line_number = line_num
        entry.source_format = self.FORMAT_SCADA
        entry.timestamp_raw = match.group(1)
        entry.level = match.group(2).upper()
        entry.module = match.group(3)
        entry.process = match.group(4)
        entry.message = match.group(5)
        entry.timestamp_epoch = self._parse_applog_timestamp(entry.timestamp_raw)
        return entry

    # ---------------------------------------------------------------
    # Timestamp parsing
    # ---------------------------------------------------------------

    def _parse_syslog_timestamp(self, ts_str):
        """Parse a syslog timestamp like 'Feb 12 14:23:01'.

        Syslog timestamps lack the year, so we assume the current year.
        """
        try:
            current_year = time.localtime().tm_year
            full_str = "%d %s" % (current_year, ts_str)
            t = time.strptime(full_str, "%Y %b %d %H:%M:%S")
            return time.mktime(t)
        except (ValueError, OverflowError):
            return 0.0

    def _parse_applog_timestamp(self, ts_str):
        """Parse an application log timestamp like '2024-01-15 14:23:01.456'."""
        try:
            # Strip milliseconds for strptime
            base = ts_str.split(".")[0]
            t = time.strptime(base, "%Y-%m-%d %H:%M:%S")
            return time.mktime(t)
        except (ValueError, OverflowError):
            return 0.0

    def _infer_syslog_level(self, message):
        """Infer severity from syslog message content heuristics."""
        msg_lower = message.lower()
        if "error" in msg_lower or "fail" in msg_lower or "fatal" in msg_lower:
            return SEVERITY_ERROR
        if "warn" in msg_lower:
            return SEVERITY_WARNING
        if "crit" in msg_lower or "emerg" in msg_lower or "alert" in msg_lower:
            return SEVERITY_CRITICAL
        if "debug" in msg_lower:
            return SEVERITY_DEBUG
        return SEVERITY_INFO

    # ---------------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------------

    def lines_processed(self):
        return self._lines_processed

    def parse_errors(self):
        return list(self._parse_errors)
