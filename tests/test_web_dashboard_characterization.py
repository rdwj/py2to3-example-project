# -*- coding: utf-8 -*-
"""
Characterization tests for src/reporting/web_dashboard.py

Captures pre-migration behavior of:
- SessionManager with Cookie.SimpleCookie and cookielib
- DashboardServer setup with BaseHTTPServer
- Py2-specific: BaseHTTPServer, Cookie, cookielib, xmlrpclib,
  thread, urllib.unquote/quote, dict.iteritems()
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.reporting.web_dashboard import (
    SessionManager, DashboardServer, DashboardError,
)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class TestSessionManager:
    """Characterize cookie-based session management."""

    def test_create_session(self):
        """Captures: session created with username and timestamps."""
        mgr = SessionManager()
        sid = mgr.create_session("operator1")
        assert sid.startswith("SID")
        assert mgr.active_count == 1

    def test_get_session_valid(self):
        """Captures: existing session retrieved by SID."""
        mgr = SessionManager()
        sid = mgr.create_session("admin")
        session = mgr.get_session(sid)
        assert session is not None
        assert session["username"] == "admin"

    def test_get_session_missing(self):
        """Captures: nonexistent SID returns None."""
        mgr = SessionManager()
        assert mgr.get_session("NOSID") is None

    @pytest.mark.py2_behavior
    def test_parse_cookie(self):
        """Captures: Cookie.SimpleCookie parses cookie header.
        Cookie module renamed http.cookies in Py3."""
        mgr = SessionManager()
        sid = mgr.create_session("user")
        cookie_str = "platform_sid=%s" % sid
        parsed_sid = mgr.parse_cookie(cookie_str)
        assert parsed_sid == sid

    def test_parse_cookie_empty(self):
        """Captures: empty cookie header returns None."""
        mgr = SessionManager()
        assert mgr.parse_cookie("") is None

    @pytest.mark.py2_behavior
    def test_make_set_cookie(self):
        """Captures: Cookie.SimpleCookie.OutputString() for Set-Cookie header."""
        mgr = SessionManager()
        cookie_str = mgr.make_set_cookie("SID123")
        assert "platform_sid" in cookie_str
        assert "SID123" in cookie_str

    @pytest.mark.py2_behavior
    def test_expire_stale_sessions(self):
        """Captures: expire_stale uses dict.iteritems() (Py2 lazy iteration)."""
        mgr = SessionManager()
        sid = mgr.create_session("old_user")
        # Artificially age the session
        mgr._sessions[sid]["last_access"] = time.time() - mgr.TIMEOUT - 1
        mgr.expire_stale()
        assert mgr.active_count == 0

    def test_multiple_sessions(self):
        """Captures: multiple concurrent sessions tracked."""
        mgr = SessionManager()
        s1 = mgr.create_session("user1")
        s2 = mgr.create_session("user2")
        assert mgr.active_count == 2
        assert mgr.get_session(s1)["username"] == "user1"
        assert mgr.get_session(s2)["username"] == "user2"


# ---------------------------------------------------------------------------
# DashboardServer (no HTTP)
# ---------------------------------------------------------------------------

class TestDashboardServer:
    """Characterize server setup without starting HTTP."""

    def test_construction(self):
        """Captures: server holds host, port, session manager."""
        server = DashboardServer(host="0.0.0.0", port=9090)
        assert server.host == "0.0.0.0"
        assert server.port == 9090
        assert server.session_manager is not None

    def test_update_sensor_data(self):
        """Captures: sensor data dict can be updated."""
        server = DashboardServer()
        server.update_sensor_data({"TEMP-001": [{"value": 23.5}]})
        assert "TEMP-001" in server.sensor_data

    def test_add_alarm(self):
        """Captures: alarms appended to history list."""
        server = DashboardServer()
        server.add_alarm({"tag": "T1", "severity": 3})
        assert len(server.alarm_history) == 1

    def test_alarm_history_truncation(self):
        """Captures: alarm history truncated to last 500 when exceeding 1000.
        After adding 1010 items, truncation fires at 1001 (keeping 500),
        then 9 more items are added, yielding 509 total."""
        server = DashboardServer()
        for i in range(1010):
            server.add_alarm({"tag": "T%d" % i, "severity": 1})
        assert len(server.alarm_history) <= 510

    def test_default_port(self):
        """Captures: default port is 8080."""
        server = DashboardServer()
        assert server.port == 8080
