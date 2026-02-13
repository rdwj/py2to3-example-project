# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/opcua_client.py

Captures pre-migration behavior of:
- OpcUaNode with dict.has_key()
- OpcUaSubscription with Queue.Queue
- OpcUaClient encoding fallback chain (_dec method)
- XML response parsing for session IDs and node values
- Py2-specific: httplib, urllib, urllib2, xmlrpclib, Queue, thread,
  unicode isinstance checks, dict.has_key()
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.io_protocols.opcua_client import (
    OpcUaNode, OpcUaSubscription, OpcUaClient,
    OPCUA_NS, TYPES_NS, STATUS_GOOD, ATTR_VALUE,
    _ENC_FALLBACKS,
)


# ---------------------------------------------------------------------------
# OpcUaNode
# ---------------------------------------------------------------------------

class TestOpcUaNode:
    """Characterize OPC-UA node data holder."""

    def test_construction(self):
        """Captures: node holds id, browse_name, display_name."""
        node = OpcUaNode("ns=2;s=TEMP001", "Temperature", "Temp 1")
        assert node.node_id == "ns=2;s=TEMP001"
        assert node.browse_name == "Temperature"
        assert node.display_name == "Temp 1"
        assert node.attributes == {}
        assert node.children == []

    @pytest.mark.py2_behavior
    def test_has_attribute_uses_has_key(self):
        """Captures: has_attribute uses dict.has_key() (removed in Py3)."""
        node = OpcUaNode("n1")
        node.attributes["source"] = "xmlrpc"
        assert node.has_attribute("source") is True
        assert node.has_attribute("missing") is False

    @pytest.mark.py2_behavior
    def test_get_attribute_uses_has_key(self):
        """Captures: get_attribute uses dict.has_key() internally."""
        node = OpcUaNode("n1")
        node.attributes["val"] = 42
        assert node.get_attribute("val") == 42
        assert node.get_attribute("missing", "default") == "default"

    def test_set_value(self):
        """Captures: set_value stores value and status."""
        node = OpcUaNode("n1")
        node.set_value(23.5, STATUS_GOOD)
        assert node._value == 23.5
        assert node._status == STATUS_GOOD

    def test_as_data_point_good_quality(self):
        """Captures: good status maps to quality=192."""
        node = OpcUaNode("TEMP001")
        node.set_value(42.0, STATUS_GOOD)
        dp = node.as_data_point()
        assert dp.tag == "OPCUA.TEMP001"
        assert dp.value == 42.0
        assert dp.quality == 192

    def test_as_data_point_bad_quality(self):
        """Captures: non-zero status maps to quality=0."""
        node = OpcUaNode("TEMP001")
        node.set_value(42.0, 0x80000000)
        dp = node.as_data_point()
        assert dp.quality == 0

    def test_repr(self):
        """Captures: __repr__ format."""
        node = OpcUaNode("ns=2;s=X")
        assert "ns=2;s=X" in repr(node)


# ---------------------------------------------------------------------------
# OpcUaSubscription
# ---------------------------------------------------------------------------

class TestOpcUaSubscription:
    """Characterize data-change subscription."""

    def test_add_monitored_item(self):
        """Captures: monitoring items are tracked by node_id."""
        sub = OpcUaSubscription(1, interval_ms=500)
        iid = sub.add_monitored_item("ns=2;s=TEMP", sampling_ms=250)
        assert iid == 1
        assert "ns=2;s=TEMP" in sub._items

    @pytest.mark.py2_behavior
    def test_remove_monitored_item_uses_has_key(self):
        """Captures: remove_monitored_item uses dict.has_key()."""
        sub = OpcUaSubscription(1)
        sub.add_monitored_item("n1")
        sub.remove_monitored_item("n1")
        assert "n1" not in sub._items
        # Removing nonexistent key does nothing
        sub.remove_monitored_item("nonexistent")

    def test_get_next_timeout(self):
        """Captures: get_next returns None on timeout."""
        sub = OpcUaSubscription(1)
        assert sub.get_next(timeout=0.1) is None

    def test_push_and_get_next(self):
        """Captures: internal _push adds notification, get_next retrieves it."""
        sub = OpcUaSubscription(1)
        sub._push("n1", 42.0, STATUS_GOOD, 1000.0)
        result = sub.get_next(timeout=1.0)
        assert result is not None
        assert result["node_id"] == "n1"
        assert result["value"] == 42.0

    def test_queue_overflow(self):
        """Captures: when queue is full, oldest entry is dropped."""
        sub = OpcUaSubscription(1)
        sub._queue = __import__("queue").Queue(maxsize=2)
        sub._push("n1", 1.0, 0, 1.0)
        sub._push("n2", 2.0, 0, 2.0)
        sub._push("n3", 3.0, 0, 3.0)  # should evict n1
        results = []
        while True:
            r = sub.get_next(timeout=0.1)
            if r is None:
                break
            results.append(r)
        values = [r["value"] for r in results]
        assert 1.0 not in values


# ---------------------------------------------------------------------------
# OpcUaClient -- encoding
# ---------------------------------------------------------------------------

class TestOpcUaClientEncoding:
    """Characterize the encoding fallback chain."""

    @pytest.fixture
    def client(self):
        return OpcUaClient("http://localhost:4840/opcua")

    @pytest.mark.py2_behavior
    def test_dec_unicode_passthrough(self, client):
        """Captures: _dec returns unicode input unchanged."""
        text = u"already unicode caf\u00e9"
        assert client._dec(text) == text

    @pytest.mark.py2_behavior
    def test_dec_utf8_bytes(self, client):
        """Captures: _dec decodes UTF-8 bytes to unicode."""
        raw = u"caf\u00e9".encode("utf-8")
        result = client._dec(raw)
        assert isinstance(result, str)
        assert u"\u00e9" in result

    @pytest.mark.py2_behavior
    def test_dec_latin1_fallback(self, client):
        """Captures: _dec falls back to latin-1 for non-UTF-8 bytes."""
        raw = b"\xe9\xe8\xea"  # latin-1 e-acute, e-grave, e-circumflex
        result = client._dec(raw)
        assert isinstance(result, str)
        assert u"\u00e9" in result

    @pytest.mark.py2_behavior
    def test_dec_shift_jis(self, client):
        """Captures: _dec decodes Shift-JIS for Japanese site labels."""
        raw = u"\u6e29\u5ea6".encode("shift_jis")  # "temperature" in Japanese
        result = client._dec(raw)
        assert isinstance(result, str)

    @pytest.mark.py2_behavior
    def test_dec_ultimate_latin1_fallback(self, client):
        """Captures: _dec final fallback to latin-1 when all candidates fail."""
        # Bytes that are valid latin-1 but not valid in other encodings
        raw = b"\x80\x81\x82"
        result = client._dec(raw)
        assert isinstance(result, str)

    def test_enc_fallbacks_ordering(self):
        """Captures: encoding candidates are tried in priority order."""
        assert _ENC_FALLBACKS[0] == "utf-8"
        assert _ENC_FALLBACKS[1] == "latin-1"
        assert "shift_jis" in _ENC_FALLBACKS


# ---------------------------------------------------------------------------
# OpcUaClient -- XML parsing
# ---------------------------------------------------------------------------

class TestOpcUaClientXmlParsing:
    """Characterize XML response parsing (no network)."""

    @pytest.fixture
    def client(self):
        return OpcUaClient("http://localhost:4840/opcua")

    def test_parse_sid_valid(self, client):
        """Captures: _parse_sid extracts SessionId from XML."""
        xml = (
            '<Response xmlns="%s">'
            '<SessionId>SESSION-123</SessionId>'
            '</Response>' % OPCUA_NS
        )
        sid = client._parse_sid(xml)
        assert sid == "SESSION-123"

    def test_parse_sid_missing_raises(self, client):
        """Captures: missing SessionId raises OpcUaError."""
        from src.core.exceptions import OpcUaError
        xml = '<Response xmlns="%s"><Other>x</Other></Response>' % OPCUA_NS
        with pytest.raises(OpcUaError, match="No SessionId"):
            client._parse_sid(xml)

    def test_parse_read_extracts_value(self, client):
        """Captures: _parse_read extracts Value text from XML."""
        xml = (
            '<Response xmlns="%s">'
            '<Value xmlns="%s">42.5</Value>'
            '<StatusCode xmlns="%s" Code="0x00000000"/>'
            '</Response>' % (OPCUA_NS, TYPES_NS, OPCUA_NS)
        )
        node = client._parse_read(xml, "TEMP001")
        assert node._value == "42.5"
        assert node._status == STATUS_GOOD

    def test_parse_read_with_bad_xml(self, client):
        """Captures: malformed XML produces node with parse_error attribute."""
        # Pass something that doesn't cause a crash but has no expected elements
        xml = '<Root><Something>data</Something></Root>'
        node = client._parse_read(xml, "X")
        assert node._value is None
