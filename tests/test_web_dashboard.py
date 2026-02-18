# -*- coding: utf-8 -*-
"""
Characterization tests for src/reporting/web_dashboard.py

Tests HTTP server, session management, cookie handling, URL encoding, and
XML-RPC integration. Mocks BaseHTTPServer and thread module to avoid
network/threading dependencies.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import time
import pytest
from unittest import mock
import http.cookies

from src.reporting.web_dashboard import (
    DashboardError, SessionManager, DashboardHandler, DashboardServer
)


# ============================================================================
# SessionManager Tests
# ============================================================================

def test_session_manager_init():
    """Test SessionManager initialization."""
    sm = SessionManager()
    assert sm.active_count == 0
    assert sm.SESSION_COOKIE == "platform_sid"
    assert sm.TIMEOUT == 3600


def test_session_manager_create_session(capsys):
    """Test creating a new session."""
    sm = SessionManager()
    sid = sm.create_session("john_doe")

    assert sid.startswith("SID")
    assert "john_doe" in sid or sm.get_session(sid)["username"] == "john_doe"
    assert sm.active_count == 1

    captured = capsys.readouterr()
    assert "Session created" in captured.out
    assert "john_doe" in captured.out


def test_session_manager_create_multiple_sessions():
    """Test creating multiple unique sessions."""
    sm = SessionManager()
    sid1 = sm.create_session("user1")
    sid2 = sm.create_session("user2")

    assert sid1 != sid2
    assert sm.active_count == 2


def test_session_manager_get_session_valid():
    """Test retrieving a valid session."""
    sm = SessionManager()
    sid = sm.create_session("test_user")

    session = sm.get_session(sid)
    assert session is not None
    assert session["username"] == "test_user"
    assert "created" in session
    assert "last_access" in session


def test_session_manager_get_session_invalid():
    """Test retrieving non-existent session returns None."""
    sm = SessionManager()
    session = sm.get_session("INVALID_SID")
    assert session is None


def test_session_manager_get_session_expired():
    """Test that expired sessions are deleted and return None."""
    sm = SessionManager()
    sid = sm.create_session("test_user")

    # Force session to expire by manipulating last_access
    session = sm._sessions[sid]
    session["last_access"] = time.time() - 4000  # More than TIMEOUT

    result = sm.get_session(sid)
    assert result is None
    assert sid not in sm._sessions


def test_session_manager_get_session_updates_last_access():
    """Test that accessing a session updates last_access timestamp."""
    sm = SessionManager()
    sid = sm.create_session("test_user")

    time.sleep(0.1)
    old_access = sm._sessions[sid]["last_access"]

    sm.get_session(sid)
    new_access = sm._sessions[sid]["last_access"]

    assert new_access > old_access


def test_session_manager_parse_cookie_valid():
    """Test parsing valid cookie header."""
    sm = SessionManager()
    cookie_header = "platform_sid=SID42_1234567890; path=/"

    sid = sm.parse_cookie(cookie_header)
    assert sid == "SID42_1234567890"


def test_session_manager_parse_cookie_missing():
    """Test parsing cookie header without session cookie."""
    sm = SessionManager()
    cookie_header = "other_cookie=value123"

    sid = sm.parse_cookie(cookie_header)
    assert sid is None


def test_session_manager_parse_cookie_empty():
    """Test parsing empty cookie header."""
    sm = SessionManager()
    sid = sm.parse_cookie("")
    assert sid is None
    sid = sm.parse_cookie(None)
    assert sid is None


def test_session_manager_make_set_cookie():
    """Test generating Set-Cookie header."""
    sm = SessionManager()
    set_cookie = sm.make_set_cookie("SID123_999")

    assert "platform_sid=SID123_999" in set_cookie
    assert "path=/" in set_cookie
    assert "httponly" in set_cookie.lower()


def test_session_manager_expire_stale_single(capsys):
    """Test expiring a single stale session."""
    sm = SessionManager()
    sid = sm.create_session("stale_user")

    # Force session to be stale
    sm._sessions[sid]["last_access"] = time.time() - 4000

    sm.expire_stale()

    assert sid not in sm._sessions
    assert sm.active_count == 0
    captured = capsys.readouterr()
    assert "Expired 1 stale" in captured.out


def test_session_manager_expire_stale_multiple(capsys):
    """Test expiring multiple stale sessions."""
    sm = SessionManager()
    sid1 = sm.create_session("user1")
    sid2 = sm.create_session("user2")
    sid3 = sm.create_session("user3")

    # Make two stale, keep one active
    sm._sessions[sid1]["last_access"] = time.time() - 4000
    sm._sessions[sid2]["last_access"] = time.time() - 5000

    sm.expire_stale()

    assert sm.active_count == 1
    assert sid3 in sm._sessions


def test_session_manager_expire_stale_none(capsys):
    """Test expiring when no stale sessions exist."""
    sm = SessionManager()
    sm.create_session("active_user")

    capsys.readouterr()  # Clear previous output
    sm.expire_stale()

    captured = capsys.readouterr()
    assert "Expired" not in captured.out


# ============================================================================
# DashboardHandler Tests
# ============================================================================

@pytest.fixture
def handler_setup():
    """Setup DashboardHandler class variables for testing."""
    DashboardHandler.session_manager = SessionManager()
    DashboardHandler.sensor_data = {
        "TEMP_001": [{"value": 72.5, "timestamp": time.time()}],
        "PRESSURE_042": [{"value": 145.2, "timestamp": time.time()}],
    }
    DashboardHandler.alarm_history = [
        {
            "timestamp": time.time(),
            "tag": "TEMP_001",
            "severity": 2,
            "message": "High temperature"
        }
    ]
    DashboardHandler.rpc_proxy = None
    return DashboardHandler


def test_dashboard_handler_init(handler_setup):
    """Test DashboardHandler has required class variables."""
    assert handler_setup.session_manager is not None
    assert handler_setup.sensor_data is not None
    assert handler_setup.alarm_history is not None


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_status_page(mock_init, handler_setup, capsys):
    """Test serving status page."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    # Mock request/response infrastructure
    handler.path = "/status"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.headers.get.return_value = ""
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    # Verify HTML response was sent
    handler.send_response.assert_called_with(200)
    handler.wfile.write.assert_called_once()
    html_output = handler.wfile.write.call_args[0][0]
    assert b"Platform Status" in html_output or "Platform Status" in html_output


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_sensors_page_no_filter(mock_init, handler_setup):
    """Test serving sensors page without tag filter."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    handler.path = "/sensors"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.headers.get.return_value = ""
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    html_output = handler.wfile.write.call_args[0][0]
    # Should contain both sensor tags
    assert b"TEMP_001" in html_output or "TEMP_001" in str(html_output)


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_sensors_page_with_filter(mock_init, handler_setup):
    """Test serving sensors page with tag filter (urllib.unquote usage)."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    handler.path = "/sensors?tag=TEMP_001"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.headers.get.return_value = ""
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    html_output = handler.wfile.write.call_args[0][0]
    assert b"TEMP_001" in html_output or "TEMP_001" in str(html_output)


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_alarms_page(mock_init, handler_setup):
    """Test serving alarms history page."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    handler.path = "/alarms"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.headers.get.return_value = ""
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    html_output = handler.wfile.write.call_args[0][0]
    assert b"Alarm History" in html_output or "Alarm History" in str(html_output)
    assert b"High temperature" in html_output or "High temperature" in str(html_output)


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_json_api(mock_init, handler_setup):
    """Test serving JSON data endpoint."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    handler.path = "/api/data"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    # Verify JSON response
    handler.send_header.assert_any_call("Content-Type", "application/json")
    json_output = handler.wfile.write.call_args[0][0]
    assert b"{" in json_output or "{" in json_output
    assert b"TEMP_001" in json_output or "TEMP_001" in str(json_output)


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_json_api_with_rpc(mock_init, handler_setup, capsys):
    """Test JSON endpoint with XML-RPC proxy (xmlrpclib usage)."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    # Mock XML-RPC proxy
    handler.rpc_proxy = mock.MagicMock()
    handler.rpc_proxy.get_latest_readings.return_value = {
        "NEW_SENSOR": [{"value": 99.9, "timestamp": time.time()}]
    }

    handler.path = "/api/data"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    # Verify RPC was called
    handler.rpc_proxy.get_latest_readings.assert_called_once()
    captured = capsys.readouterr()
    assert "Refreshed data via XML-RPC" in captured.out


@mock.patch("http.server.BaseHTTPRequestHandler.__init__")
def test_dashboard_handler_404_not_found(mock_init, handler_setup):
    """Test 404 response for unknown paths."""
    mock_init.return_value = None
    handler = handler_setup(None, None, None)

    handler.path = "/nonexistent"
    handler.command = "GET"
    handler.headers = mock.MagicMock()
    handler.wfile = mock.MagicMock()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()

    handler.do_GET()

    handler.send_response.assert_called_with(404)
    html_output = handler.wfile.write.call_args[0][0]
    assert b"404" in html_output or "404" in html_output


# ============================================================================
# DashboardServer Tests
# ============================================================================

def test_dashboard_server_init_defaults(capsys):
    """Test DashboardServer initialization with defaults."""
    server = DashboardServer()
    assert server.host == "0.0.0.0"
    assert server.port == 8080
    assert server.session_manager is not None
    assert server.sensor_data == {}
    assert server.alarm_history == []
    assert server.rpc_proxy is None
    assert server._running is False


def test_dashboard_server_init_custom_port(capsys):
    """Test DashboardServer with custom port."""
    server = DashboardServer(host="127.0.0.1", port=9000)
    assert server.host == "127.0.0.1"
    assert server.port == 9000


def test_dashboard_server_init_with_rpc(capsys):
    """Test DashboardServer with XML-RPC endpoint."""
    with mock.patch("xmlrpc.client.ServerProxy") as mock_proxy:
        server = DashboardServer(rpc_endpoint="http://localhost:8000/rpc")
        assert server.rpc_proxy is not None
        captured = capsys.readouterr()
        assert "XML-RPC endpoint configured" in captured.out


def test_dashboard_server_update_sensor_data():
    """Test updating sensor data."""
    server = DashboardServer()
    data = {"SENSOR_A": [{"value": 123.4, "timestamp": time.time()}]}
    server.update_sensor_data(data)
    assert server.sensor_data == data


def test_dashboard_server_add_alarm():
    """Test adding alarm to history."""
    server = DashboardServer()
    alarm = {"timestamp": time.time(), "tag": "TEST", "severity": 3, "message": "Test alarm"}

    server.add_alarm(alarm)
    assert len(server.alarm_history) == 1
    assert server.alarm_history[0] == alarm


def test_dashboard_server_add_alarm_trimming():
    """Test alarm history trimming when exceeding 1000 entries."""
    server = DashboardServer()

    # Add 1001 alarms
    for i in range(1001):
        server.add_alarm({"timestamp": time.time(), "tag": f"TAG_{i}", "severity": 1, "message": "Test"})

    # Should trim to 500
    assert len(server.alarm_history) == 500


@mock.patch("http.server.HTTPServer")
@mock.patch("_thread.start_new_thread")
def test_dashboard_server_start_background(mock_thread, mock_http_server, capsys):
    """Test starting server in background thread (thread module usage)."""
    server = DashboardServer(port=8888)
    server.update_sensor_data({"TEST": [{"value": 1.0, "timestamp": time.time()}]})

    server.start(background=True)

    assert server._running is True
    mock_http_server.assert_called_once()
    mock_thread.assert_called_once()

    captured = capsys.readouterr()
    assert "Dashboard at http://0.0.0.0:8888" in captured.out
    assert "background thread" in captured.out


@mock.patch("http.server.HTTPServer")
def test_dashboard_server_start_foreground(mock_http_server, capsys):
    """Test starting server in foreground (would block)."""
    server = DashboardServer()
    mock_http_server.return_value.handle_request.side_effect = KeyboardInterrupt  # Prevent blocking

    try:
        server.start(background=False)
    except KeyboardInterrupt:
        pass

    assert server._running is True
    captured = capsys.readouterr()
    assert "Dashboard at http://" in captured.out


@mock.patch("http.server.HTTPServer")
def test_dashboard_server_stop(mock_http_server, capsys):
    """Test stopping the dashboard server."""
    server = DashboardServer()
    server._server = mock_http_server.return_value
    server._running = True

    server.stop()

    assert server._running is False
    server._server.server_close.assert_called_once()
    captured = capsys.readouterr()
    assert "Dashboard stopped" in captured.out


def test_dashboard_server_url_encoding(capsys):
    """Test URL parameter encoding (urllib.urlencode usage)."""
    with mock.patch("BaseHTTPServer.HTTPServer"):
        with mock.patch("thread.start_new_thread"):
            server = DashboardServer(port=8080)
            server.start(background=True)

            captured = capsys.readouterr()
            # Should contain URL-encoded parameters
            assert "view=status" in captured.out or "format=html" in captured.out
