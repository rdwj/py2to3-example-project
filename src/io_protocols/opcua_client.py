# -*- coding: utf-8 -*-
"""
OPC-UA client for the Legacy Industrial Data Platform.
HTTP/SOAP transport with XML-RPC fallback for legacy gateways.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import time
import socket
import http.client
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import URLError
import xmlrpc.client
import queue
import _thread
from xml.etree import ElementTree

from src.core.types import DataPoint
from src.core.exceptions import OpcUaError

OPCUA_NS = "http://opcfoundation.org/UA/"
TYPES_NS = "http://opcfoundation.org/UA/2008/02/Types.xsd"
STATUS_GOOD = 0x00000000
ATTR_VALUE = 13
_ENC_FALLBACKS = ["utf-8", "latin-1", "shift_jis", "cp1252"]


class OpcUaNode(object):
    """OPC-UA node."""

    def __init__(self, node_id, browse_name=None, display_name=None):
        self.node_id = node_id
        self.browse_name = browse_name
        self.display_name = display_name
        self.attributes = {}
        self.children = []
        self._value = None
        self._status = None

    def has_attribute(self, name):
        return name in self.attributes

    def get_attribute(self, name, default=None):
        if name in self.attributes:
            return self.attributes[name]
        return default

    def set_value(self, value, status=STATUS_GOOD):
        self._value = value
        self._status = status

    def as_data_point(self, prefix="OPCUA"):
        q = 192 if self._status == STATUS_GOOD else 0
        return DataPoint("%s.%s" % (prefix, self.node_id), self._value, quality=q)

    def __repr__(self):
        return "OpcUaNode(%r)" % self.node_id


class OpcUaSubscription(object):
    """Data-change subscription with queue.Queue() buffer."""

    def __init__(self, sid, interval_ms=1000):
        self.subscription_id = sid
        self.interval_ms = interval_ms
        self._items = {}
        self._queue = queue.Queue(maxsize=5000)

    def add_monitored_item(self, node_id, sampling_ms=500):
        iid = len(self._items) + 1
        self._items[node_id] = {"item_id": iid, "ms": sampling_ms}
        print("OPC-UA: monitoring %s (item %d)" % (node_id, iid))
        return iid

    def remove_monitored_item(self, node_id):
        if node_id in self._items:
            del self._items[node_id]

    def get_next(self, timeout=5.0):
        try:
            return self._queue.get(block=True, timeout=timeout)
        except queue.Empty:
            return None

    def _push(self, nid, val, status, ts):
        n = {"node_id": nid, "value": val, "status": status, "ts": ts}
        try:
            self._queue.put_nowait(n)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(n)


class OpcUaClient(object):
    """HTTP-based OPC-UA client with XML-RPC fallback."""

    def __init__(self, endpoint, auth_token=None, timeout=10.0):
        self.endpoint = endpoint
        self.auth_token = auth_token
        self.timeout = timeout
        self._sid = None
        self._cache = {}
        self._subs = {}
        self._polling = False

    def connect(self):
        print("OPC-UA: connecting to %s" % self.endpoint)
        try:
            p = urlencode({"RequestType": "CreateSession",
                                  "Timeout": int(self.timeout * 1000)})
            req = Request("%s?%s" % (self.endpoint, p))
            if self.auth_token:
                req.add_header("Authorization", "Bearer %s" % self.auth_token)
            req.add_header("Content-Type", "application/opcua+uaxml")
            body = urlopen(req, timeout=self.timeout).read()
            self._sid = self._parse_sid(body)
            print("OPC-UA: session %s" % self._sid)
        except URLError as e:
            raise OpcUaError("Connection failed: %s" % e)

    def disconnect(self):
        self._polling = False
        if self._sid:
            try:
                p = urlencode({"RequestType": "CloseSession",
                                      "SessionId": self._sid})
                urlopen("%s?%s" % (self.endpoint, p), timeout=self.timeout)
            except URLError as e:
                print("OPC-UA: disconnect warning -- %s" % e)
            self._sid = None

    def read_node(self, node_id, attr=ATTR_VALUE):
        """Read node attribute.  Handles mixed encodings (Shift-JIS,
        Latin-1) in the XML response."""
        if not self._sid:
            raise OpcUaError("No session")
        url = "%s/read/%s?attr=%d&session=%s" % (
            self.endpoint, quote(node_id, safe=""), attr, self._sid)
        try:
            raw = urlopen(url, timeout=self.timeout).read()
        except URLError as e:
            raise OpcUaError("Read failed for %s: %s" % (node_id, e))
        node = self._parse_read(raw, node_id)
        self._cache[node_id] = node
        return node

    def read_via_xmlrpc(self, gw_url, node_id):
        """XML-RPC read using xmlrpc.client.ServerProxy."""
        print("OPC-UA: XML-RPC read %s via %s" % (node_id, gw_url))
        try:
            proxy = xmlrpc.client.ServerProxy(gw_url, allow_none=True)
            r = proxy.readNodeValue(node_id)
            if r is None:
                raise OpcUaError("XML-RPC None for %s" % node_id)
            node = OpcUaNode(node_id)
            node.set_value(r.get("value"), r.get("status", STATUS_GOOD))
            node.attributes["source"] = "xmlrpc"
            return node
        except xmlrpc.client.Fault as e:
            raise OpcUaError("XML-RPC fault: %s" % e.faultString)
        except xmlrpc.client.ProtocolError as e:
            raise OpcUaError("XML-RPC: %d %s" % (e.errcode, e.errmsg))

    def create_subscription(self, interval_ms=1000):
        sid = len(self._subs) + 1
        sub = OpcUaSubscription(sid, interval_ms)
        self._subs[sid] = sub
        return sub

    def start_subscription_polling(self):
        """Background via _thread.start_new_thread()."""
        self._polling = True
        _thread.start_new_thread(self._poll, ())

    def check_connection(self):
        """Connection check using http.client.HTTPConnection."""
        try:
            host = self.endpoint.replace("http://", "").split("/")[0]
            c = http.client.HTTPConnection(host, timeout=self.timeout)
            c.request("HEAD", "/")
            ok = c.getresponse().status < 500
            c.close()
            return ok
        except (http.client.HTTPException, socket.error) as e:
            print("OPC-UA: check failed -- %s" % e)
            return False

    def _parse_sid(self, xml_body):
        t = self._dec(xml_body)
        try:
            root = ElementTree.fromstring(t.encode("utf-8"))
            el = root.find(".//{%s}SessionId" % OPCUA_NS)
            if el is not None and el.text:
                return el.text.strip()
        except ElementTree.ParseError as e:
            raise OpcUaError("Parse error: %s" % e)
        raise OpcUaError("No SessionId in response")

    def _parse_read(self, raw, node_id):
        t = self._dec(raw)
        node = OpcUaNode(node_id)
        try:
            root = ElementTree.fromstring(t.encode("utf-8"))
            v = root.find(".//{%s}Value" % TYPES_NS)
            sc = root.find(".//{%s}StatusCode" % OPCUA_NS)
            if v is not None and v.text:
                node.set_value(v.text.strip())
                node.attributes["raw_value"] = v.text
            if sc is not None:
                try:
                    node._status = int(sc.get("Code", "0"), 0)
                except ValueError:
                    pass
        except ElementTree.ParseError as e:
            node.attributes["parse_error"] = str(e)
        return node

    def _dec(self, raw):
        """Decode trying multiple encodings for international sites."""
        if isinstance(raw, str):
            return raw
        for enc in _ENC_FALLBACKS:
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("latin-1")

    def _poll(self):
        while self._polling:
            for sid, sub in self._subs.items():
                if not sub._items:
                    continue
                try:
                    p = urlencode({"RequestType": "Publish",
                                          "SubscriptionId": sid,
                                          "SessionId": self._sid})
                    raw = urlopen("%s?%s" % (self.endpoint, p),
                                         timeout=self.timeout).read()
                    root = ElementTree.fromstring(self._dec(raw).encode("utf-8"))
                    for ch in root.findall(".//{%s}DataChangeNotification" % OPCUA_NS):
                        nid = ch.find("{%s}NodeId" % OPCUA_NS)
                        val = ch.find("{%s}Value" % OPCUA_NS)
                        if nid is not None and val is not None:
                            sub._push(nid.text.strip() if nid.text else "",
                                      val.text.strip() if val.text else None,
                                      STATUS_GOOD, time.time())
                except (URLError, ElementTree.ParseError):
                    pass
            time.sleep(0.5)
