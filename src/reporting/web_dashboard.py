# -*- coding: utf-8 -*-
"""
Basic web dashboard for the Legacy Industrial Data Platform.

Provides a lightweight HTTP server that displays real-time sensor data,
alarm history, and system status in a browser.  This predates the move
to a proper web framework -- it was a quick diagnostic page that the
lead controls engineer hacked together one weekend and it stuck.

Uses ``BaseHTTPServer`` for HTTP, ``Cookie`` for sessions, and
``thread`` for running the server in the background so the main
data-acquisition loop isn't blocked.
"""

import time
import urllib
import thread
import BaseHTTPServer
import Cookie
import cookielib
import xmlrpclib

from core.exceptions import PlatformError
from core.string_helpers import safe_decode, safe_encode


class DashboardError(PlatformError):
    """Raised when the dashboard encounters an unrecoverable error."""
    pass


class SessionManager(object):
    """Cookie-based session store.  In-memory only -- a restart clears
    all sessions.  Uses Cookie.SimpleCookie for parsing and
    cookielib.CookieJar for outbound cookie management."""

    SESSION_COOKIE = "platform_sid"
    TIMEOUT = 3600

    def __init__(self):
        self._sessions = {}
        self._cookie_jar = cookielib.CookieJar()
        self._next_id = 1

    def create_session(self, username):
        sid = "SID%d_%d" % (self._next_id, int(time.time()))
        self._next_id += 1
        self._sessions[sid] = {"username": username, "created": time.time(),
                               "last_access": time.time()}
        print "Session created: %s (%s)" % (sid, username)
        return sid

    def get_session(self, sid):
        session = self._sessions.get(sid)
        if session is None:
            return None
        if time.time() - session["last_access"] > self.TIMEOUT:
            del self._sessions[sid]
            return None
        session["last_access"] = time.time()
        return session

    def parse_cookie(self, cookie_header):
        if not cookie_header:
            return None
        cookie = Cookie.SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(self.SESSION_COOKIE)
        return morsel.value if morsel else None

    def make_set_cookie(self, sid):
        cookie = Cookie.SimpleCookie()
        cookie[self.SESSION_COOKIE] = sid
        cookie[self.SESSION_COOKIE]["path"] = "/"
        cookie[self.SESSION_COOKIE]["httponly"] = True
        return cookie[self.SESSION_COOKIE].OutputString()

    def expire_stale(self):
        now = time.time()
        expired = [s for s, d in self._sessions.iteritems()
                   if now - d["last_access"] > self.TIMEOUT]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            print "Expired %d stale sessions" % len(expired)

    @property
    def active_count(self):
        return len(self._sessions)


class DashboardHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Serves dashboard HTML pages and a JSON data endpoint."""

    session_manager = None
    sensor_data = None
    alarm_history = None
    rpc_proxy = None

    def do_GET(self):
        print "Dashboard request: %s %s" % (self.command, self.path)
        path = self.path.split("?")[0]
        qs = self.path.split("?")[1] if "?" in self.path else ""

        if path in ("/", "/status"):
            self._serve_status()
        elif path == "/sensors":
            self._serve_sensors(qs)
        elif path == "/alarms":
            self._serve_alarms()
        elif path == "/api/data":
            self._serve_json()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write("<h1>404 Not Found</h1>")

    def _serve_status(self):
        sid = self._ensure_session()
        n_sensors = len(self.sensor_data) if self.sensor_data else 0
        n_alarms = len(self.alarm_history) if self.alarm_history else 0
        html = u"\n".join([
            u"<html><head><title>Platform Status \u2014 Dashboard</title></head><body>",
            u"<h1>Platform Status</h1>",
            u"<table border='1' cellpadding='4'>",
            u"<tr><td>Sensors</td><td>%d</td></tr>" % n_sensors,
            u"<tr><td>Alarms</td><td>%d</td></tr>" % n_alarms,
            u"<tr><td>Time</td><td>%s</td></tr>" % time.strftime("%Y-%m-%d %H:%M:%S"),
            u"<tr><td>Sessions</td><td>%d</td></tr>" % self.session_manager.active_count,
            u"</table>",
            u"<p><a href='/sensors'>Sensors</a> | <a href='/alarms'>Alarms</a></p>",
            u"</body></html>",
        ])
        self._send_html(html, sid)

    def _serve_sensors(self, qs):
        params = {}
        if qs:
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[urllib.unquote(k)] = urllib.unquote(v)
        tag_filter = params.get("tag")

        rows = [u"<html><head><title>Sensor Data</title></head><body>",
                u"<h1>Sensor Readings</h1>",
                u"<table border='1'><tr><th>Tag</th><th>Value</th><th>Time</th></tr>"]
        if self.sensor_data:
            for tag, readings in self.sensor_data.iteritems():
                if tag_filter and tag != tag_filter:
                    continue
                tag_disp = safe_decode(tag)
                for r in readings[-10:]:
                    val = r.get("value", 0) if isinstance(r, dict) else r
                    ts = r.get("timestamp", 0) if isinstance(r, dict) else 0
                    ts_s = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--"
                    rows.append(u"<tr><td>%s</td><td>%.2f</td><td>%s</td></tr>" % (
                        tag_disp, float(val), ts_s))
        rows.append(u"</table>")
        back = urllib.quote("/status")
        rows.append(u"<p><a href='%s'>Back</a></p></body></html>" % back)
        self._send_html(u"\n".join(rows))

    def _serve_alarms(self):
        rows = [u"<html><head><title>Alarm History</title></head><body>",
                u"<h1>Alarm History</h1>",
                u"<table border='1'><tr><th>Time</th><th>Tag</th><th>Sev</th><th>Message</th></tr>"]
        if self.alarm_history:
            for a in self.alarm_history:
                ts = a.get("timestamp", 0)
                ts_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "--"
                rows.append(u"<tr><td>%s</td><td>%s</td><td>%d</td><td>%s</td></tr>" % (
                    ts_s, safe_decode(a.get("tag", "")),
                    a.get("severity", 0), safe_decode(a.get("message", ""))))
        rows.append(u"</table><p><a href='/'>Back</a></p></body></html>")
        self._send_html(u"\n".join(rows))

    def _serve_json(self):
        if self.rpc_proxy is not None:
            try:
                fresh = self.rpc_proxy.get_latest_readings()
                if isinstance(fresh, dict):
                    self.sensor_data.update(fresh)
                print "Refreshed data via XML-RPC"
            except Exception, e:
                print "XML-RPC refresh failed: %s" % e
        entries = []
        if self.sensor_data:
            for tag, readings in self.sensor_data.iteritems():
                if readings:
                    last = readings[-1]
                    val = last.get("value", 0) if isinstance(last, dict) else last
                    entries.append('"%s": %.4f' % (tag.replace('"', '\\"'), float(val)))
        body = "{" + ", ".join(entries) + "}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_unicode, session_id=None):
        html_bytes = safe_encode(html_unicode)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        if session_id:
            self.send_header("Set-Cookie", self.session_manager.make_set_cookie(session_id))
        self.end_headers()
        self.wfile.write(html_bytes)

    def _ensure_session(self):
        cookie_hdr = self.headers.get("Cookie", "")
        sid = self.session_manager.parse_cookie(cookie_hdr)
        if sid and self.session_manager.get_session(sid):
            return sid
        return self.session_manager.create_session("anonymous")

    def log_message(self, format, *args):
        print "Dashboard [%s] %s" % (time.strftime("%H:%M:%S"), format % args)


class DashboardServer(object):
    """Wraps BaseHTTPServer.HTTPServer with platform-specific setup.

    Runs in a background thread via thread.start_new_thread because the
    original developer considered the threading module overkill for a
    simple HTTP server -- his words from a 2010 commit message.
    """

    DEFAULT_PORT = 8080

    def __init__(self, host="0.0.0.0", port=None, rpc_endpoint=None):
        self.host = host
        self.port = port or self.DEFAULT_PORT
        self.session_manager = SessionManager()
        self.sensor_data = {}
        self.alarm_history = []
        self._server = None
        self._running = False
        self.rpc_proxy = None
        if rpc_endpoint:
            self.rpc_proxy = xmlrpclib.ServerProxy(rpc_endpoint)
            print "XML-RPC endpoint configured: %s" % rpc_endpoint

    def update_sensor_data(self, data):
        self.sensor_data = data

    def add_alarm(self, alarm):
        self.alarm_history.append(alarm)
        if len(self.alarm_history) > 1000:
            self.alarm_history = self.alarm_history[-500:]

    def start(self, background=True):
        DashboardHandler.session_manager = self.session_manager
        DashboardHandler.sensor_data = self.sensor_data
        DashboardHandler.alarm_history = self.alarm_history
        DashboardHandler.rpc_proxy = self.rpc_proxy
        self._server = BaseHTTPServer.HTTPServer((self.host, self.port), DashboardHandler)
        self._running = True
        params = urllib.urlencode({"view": "status", "format": "html"})
        print "Dashboard at http://%s:%d/?%s" % (self.host, self.port, params)
        if background:
            thread.start_new_thread(self._serve_loop, ())
            print "Dashboard running in background thread"
        else:
            self._serve_loop()

    def _serve_loop(self):
        while self._running:
            self._server.handle_request()

    def stop(self):
        self._running = False
        if self._server:
            self._server.server_close()
        print "Dashboard stopped"
