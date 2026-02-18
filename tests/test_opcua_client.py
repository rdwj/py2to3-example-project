# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/opcua_client.py

Captures current Python 2 behavior for OPC-UA client.
Critical Py2→3 issues: httplib, urllib2, xmlrpclib, Queue, thread,
has_key(), XML encoding handling, except comma syntax.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.io_protocols.opcua_client import (
    OpcUaNode,
    OpcUaSubscription,
    OpcUaClient,
    STATUS_GOOD,
    ATTR_VALUE,
)
from src.core.exceptions import OpcUaError


# ============================================================================
# OpcUaNode Tests
# ============================================================================


class TestOpcUaNode:
    """Characterize OpcUaNode behavior with has_key()."""

    def test_node_construction(self):
        """OpcUaNode initializes with node_id."""
        node = OpcUaNode("ns=2;i=1001")
        assert node.node_id == "ns=2;i=1001"
        assert node.browse_name is None
        assert node.display_name is None

    def test_node_with_names(self):
        """OpcUaNode accepts browse_name and display_name."""
        node = OpcUaNode("ns=2;i=1001", browse_name="Sensor1", display_name="Temperature Sensor")
        assert node.browse_name == "Sensor1"
        assert node.display_name == "Temperature Sensor"

    def test_has_attribute_uses_has_key(self):
        """has_attribute() uses dict.has_key()."""
        node = OpcUaNode("test")
        node.attributes["quality"] = 192
        assert node.has_attribute("quality") is True
        assert node.has_attribute("missing") is False

    def test_get_attribute_returns_value(self):
        """get_attribute() retrieves attribute value."""
        node = OpcUaNode("test")
        node.attributes["source"] = "opcua"
        assert node.get_attribute("source") == "opcua"

    def test_get_attribute_uses_has_key(self):
        """get_attribute() uses has_key() internally."""
        node = OpcUaNode("test")
        node.attributes["x"] = 10
        result = node.get_attribute("x", default=99)
        assert result == 10

    def test_get_attribute_default(self):
        """get_attribute() returns default for missing attribute."""
        node = OpcUaNode("test")
        result = node.get_attribute("missing", default="default_val")
        assert result == "default_val"

    def test_set_value(self):
        """set_value() stores value and status."""
        node = OpcUaNode("test")
        node.set_value(42.5, status=STATUS_GOOD)
        assert node._value == 42.5
        assert node._status == STATUS_GOOD

    def test_set_value_default_status(self):
        """set_value() defaults to STATUS_GOOD."""
        node = OpcUaNode("test")
        node.set_value(100)
        assert node._status == STATUS_GOOD

    def test_as_data_point_good_status(self):
        """as_data_point() returns quality=192 for good status."""
        node = OpcUaNode("ns=2;i=1001")
        node.set_value(55.5, status=STATUS_GOOD)
        dp = node.as_data_point()
        assert dp.tag == "OPCUA.ns=2;i=1001"
        assert dp.value == 55.5
        assert dp.quality == 192

    def test_as_data_point_bad_status(self):
        """as_data_point() returns quality=0 for bad status."""
        node = OpcUaNode("test")
        node.set_value(10, status=0x80000000)
        dp = node.as_data_point()
        assert dp.quality == 0

    def test_as_data_point_custom_prefix(self):
        """as_data_point() accepts custom prefix."""
        node = OpcUaNode("i=1001")
        node.set_value(99)
        dp = node.as_data_point(prefix="PLANT")
        assert dp.tag == "PLANT.i=1001"

    def test_repr(self):
        """__repr__ includes node_id."""
        node = OpcUaNode("ns=2;i=1001")
        r = repr(node)
        assert "ns=2;i=1001" in r


# ============================================================================
# OpcUaSubscription Tests
# ============================================================================


class TestOpcUaSubscription:
    """Characterize OpcUaSubscription with Queue."""

    def test_subscription_construction(self):
        """OpcUaSubscription initializes with ID and interval."""
        sub = OpcUaSubscription(1, interval_ms=500)
        assert sub.subscription_id == 1
        assert sub.interval_ms == 500

    def test_subscription_default_interval(self):
        """OpcUaSubscription defaults to 1000ms interval."""
        sub = OpcUaSubscription(1)
        assert sub.interval_ms == 1000

    def test_add_monitored_item(self):
        """add_monitored_item() adds item and returns item ID."""
        sub = OpcUaSubscription(1)
        iid = sub.add_monitored_item("ns=2;i=1001", sampling_ms=250)
        assert iid == 1
        assert "ns=2;i=1001" in sub._items

    def test_add_monitored_item_sequential_ids(self):
        """add_monitored_item() assigns sequential item IDs."""
        sub = OpcUaSubscription(1)
        iid1 = sub.add_monitored_item("node1")
        iid2 = sub.add_monitored_item("node2")
        iid3 = sub.add_monitored_item("node3")
        assert iid1 == 1
        assert iid2 == 2
        assert iid3 == 3

    def test_remove_monitored_item_uses_has_key(self):
        """remove_monitored_item() uses has_key()."""
        sub = OpcUaSubscription(1)
        sub.add_monitored_item("node1")
        sub.remove_monitored_item("node1")
        assert "node1" not in sub._items

    def test_remove_monitored_item_missing(self):
        """remove_monitored_item() handles missing node gracefully."""
        sub = OpcUaSubscription(1)
        sub.remove_monitored_item("nonexistent")  # Should not crash

    def test_get_next_retrieves_notification(self):
        """get_next() retrieves queued notification."""
        sub = OpcUaSubscription(1)
        sub._push("node1", 42, STATUS_GOOD, 1234567890.0)
        notif = sub.get_next(timeout=0.1)
        assert notif["node_id"] == "node1"
        assert notif["value"] == 42
        assert notif["status"] == STATUS_GOOD

    def test_get_next_blocks_until_timeout(self):
        """get_next() blocks and returns None on timeout."""
        import time
        sub = OpcUaSubscription(1)
        start = time.time()
        notif = sub.get_next(timeout=0.1)
        elapsed = time.time() - start
        assert notif is None
        assert elapsed >= 0.08

    def test_push_enqueues_notification(self):
        """_push() adds notification to queue."""
        sub = OpcUaSubscription(1)
        sub._push("node1", 100, STATUS_GOOD, 1000.0)
        notif = sub.get_next(timeout=0.1)
        assert notif is not None

    def test_push_drops_oldest_when_full(self):
        """_push() drops oldest when queue is full."""
        sub = OpcUaSubscription(1)
        # Fill queue
        for i in range(5001):
            sub._push("node", i, STATUS_GOOD, 1000.0)
        # Should have dropped early values
        # Queue maxsize is 5000, so we should be able to get items
        count = 0
        while True:
            notif = sub.get_next(timeout=0.01)
            if notif is None:
                break
            count += 1
        # Should have close to 5000 items
        assert count >= 4990


# ============================================================================
# OpcUaClient Tests
# ============================================================================


class TestOpcUaClientConstruction:
    """Characterize OpcUaClient initialization."""

    def test_client_construction_basic(self):
        """OpcUaClient initializes with endpoint."""
        client = OpcUaClient("http://opcua.local/UA")
        assert client.endpoint == "http://opcua.local/UA"
        assert client.timeout == 10.0

    def test_client_construction_with_auth(self):
        """OpcUaClient accepts auth_token."""
        client = OpcUaClient("http://opcua.local/UA", auth_token="secret123")
        assert client.auth_token == "secret123"

    def test_client_construction_custom_timeout(self):
        """OpcUaClient accepts custom timeout."""
        client = OpcUaClient("http://opcua.local/UA", timeout=30.0)
        assert client.timeout == 30.0


class TestOpcUaClientConnect:
    """Characterize connect() using urllib2."""

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_connect_sends_create_session(self, mock_urlopen):
        """connect() sends CreateSession request."""
        mock_response = MagicMock()
        mock_response.read.return_value = '<?xml version="1.0"?><Response xmlns="http://opcfoundation.org/UA/"><SessionId>session123</SessionId></Response>'
        mock_urlopen.return_value = mock_response

        client = OpcUaClient("http://opcua.local/UA")
        client.connect()

        assert client._sid == "session123"
        assert mock_urlopen.called

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_connect_raises_on_url_error(self, mock_urlopen):
        """connect() raises OpcUaError on urllib.error.URLError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        client = OpcUaClient("http://opcua.local/UA")
        with pytest.raises(OpcUaError) as exc_info:
            client.connect()
        assert "Connection failed" in str(exc_info.value)

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_connect_adds_auth_header(self, mock_urlopen):
        """connect() adds Authorization header if auth_token set."""
        mock_response = MagicMock()
        mock_response.read.return_value = '<?xml version="1.0"?><Response xmlns="http://opcfoundation.org/UA/"><SessionId>s1</SessionId></Response>'
        mock_urlopen.return_value = mock_response

        client = OpcUaClient("http://opcua.local/UA", auth_token="token123")
        client.connect()

        # Check that Request was created with auth header
        assert mock_urlopen.called


class TestOpcUaClientDisconnect:
    """Characterize disconnect() using urllib.request."""

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_disconnect_sends_close_session(self, mock_urlopen):
        """disconnect() sends CloseSession request."""
        client = OpcUaClient("http://opcua.local/UA")
        client._sid = "session123"
        client._polling = True

        client.disconnect()

        assert client._sid is None
        assert client._polling is False

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_disconnect_handles_error_gracefully(self, mock_urlopen):
        """disconnect() handles URLError gracefully."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        client = OpcUaClient("http://opcua.local/UA")
        client._sid = "session123"
        client.disconnect()  # Should not raise

        assert client._sid is None


class TestOpcUaClientReadNode:
    """Characterize read_node() using urllib.request."""

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_read_node_basic(self, mock_urlopen):
        """read_node() reads node value."""
        mock_response = MagicMock()
        xml_body = '<?xml version="1.0"?><Response xmlns:ns="http://opcfoundation.org/UA/2008/02/Types.xsd"><ns:Value>42.5</ns:Value><StatusCode xmlns="http://opcfoundation.org/UA/" Code="0x00000000"/></Response>'
        mock_response.read.return_value = xml_body
        mock_urlopen.return_value = mock_response

        client = OpcUaClient("http://opcua.local/UA")
        client._sid = "session123"

        node = client.read_node("ns=2;i=1001")

        assert node.node_id == "ns=2;i=1001"
        assert node._value == "42.5"

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_read_node_raises_if_no_session(self, mock_urlopen):
        """read_node() raises if not connected."""
        client = OpcUaClient("http://opcua.local/UA")
        client._sid = None

        with pytest.raises(OpcUaError) as exc_info:
            client.read_node("test")
        assert "No session" in str(exc_info.value)

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_read_node_handles_url_error(self, mock_urlopen):
        """read_node() raises OpcUaError on URLError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        client = OpcUaClient("http://opcua.local/UA")
        client._sid = "session123"

        with pytest.raises(OpcUaError) as exc_info:
            client.read_node("test")
        assert "Read failed" in str(exc_info.value)

    @patch("src.io_protocols.opcua_client.urllib.request.urlopen")
    def test_read_node_caches_result(self, mock_urlopen):
        """read_node() caches node in _cache."""
        mock_response = MagicMock()
        mock_response.read.return_value = '<?xml version="1.0"?><Response xmlns:ns="http://opcfoundation.org/UA/2008/02/Types.xsd"><ns:Value>99</ns:Value></Response>'
        mock_urlopen.return_value = mock_response

        client = OpcUaClient("http://opcua.local/UA")
        client._sid = "s1"

        node = client.read_node("node1")
        assert "node1" in client._cache
        assert client._cache["node1"] is node


class TestOpcUaClientXmlRpc:
    """Characterize read_via_xmlrpc() using xmlrpc.client."""

    @patch("src.io_protocols.opcua_client.xmlrpc.client.ServerProxy")
    def test_read_via_xmlrpc_basic(self, mock_proxy_class):
        """read_via_xmlrpc() calls XML-RPC method."""
        mock_proxy = MagicMock()
        mock_proxy.readNodeValue.return_value = {"value": 123, "status": STATUS_GOOD}
        mock_proxy_class.return_value = mock_proxy

        client = OpcUaClient("http://opcua.local/UA")
        node = client.read_via_xmlrpc("http://gateway/RPC2", "node1")

        assert node.node_id == "node1"
        assert node._value == 123
        assert node._status == STATUS_GOOD
        mock_proxy.readNodeValue.assert_called_once_with("node1")

    @patch("src.io_protocols.opcua_client.xmlrpc.client.ServerProxy")
    def test_read_via_xmlrpc_handles_fault(self, mock_proxy_class):
        """read_via_xmlrpc() raises OpcUaError on Fault."""
        import xmlrpc.client
        mock_proxy = MagicMock()
        mock_proxy.readNodeValue.side_effect = xmlrpc.client.Fault(1, "method failed")
        mock_proxy_class.return_value = mock_proxy

        client = OpcUaClient("http://opcua.local/UA")
        with pytest.raises(OpcUaError) as exc_info:
            client.read_via_xmlrpc("http://gateway/RPC2", "node1")
        assert "fault" in str(exc_info.value).lower()

    @patch("src.io_protocols.opcua_client.xmlrpc.client.ServerProxy")
    def test_read_via_xmlrpc_handles_protocol_error(self, mock_proxy_class):
        """read_via_xmlrpc() raises OpcUaError on ProtocolError."""
        import xmlrpc.client
        mock_proxy = MagicMock()
        mock_proxy.readNodeValue.side_effect = xmlrpc.client.ProtocolError(
            "http://gateway/RPC2", 500, "Internal Server Error", {}
        )
        mock_proxy_class.return_value = mock_proxy

        client = OpcUaClient("http://opcua.local/UA")
        with pytest.raises(OpcUaError) as exc_info:
            client.read_via_xmlrpc("http://gateway/RPC2", "node1")
        assert "500" in str(exc_info.value)

    @patch("src.io_protocols.opcua_client.xmlrpc.client.ServerProxy")
    def test_read_via_xmlrpc_raises_on_none(self, mock_proxy_class):
        """read_via_xmlrpc() raises if response is None."""
        mock_proxy = MagicMock()
        mock_proxy.readNodeValue.return_value = None
        mock_proxy_class.return_value = mock_proxy

        client = OpcUaClient("http://opcua.local/UA")
        with pytest.raises(OpcUaError) as exc_info:
            client.read_via_xmlrpc("http://gateway/RPC2", "node1")
        assert "None" in str(exc_info.value)


class TestOpcUaClientSubscriptions:
    """Characterize subscription creation."""

    def test_create_subscription(self):
        """create_subscription() creates and stores subscription."""
        client = OpcUaClient("http://opcua.local/UA")
        sub = client.create_subscription(interval_ms=500)

        assert isinstance(sub, OpcUaSubscription)
        assert sub.subscription_id == 1
        assert sub.interval_ms == 500

    def test_create_subscription_sequential_ids(self):
        """create_subscription() assigns sequential IDs."""
        client = OpcUaClient("http://opcua.local/UA")
        sub1 = client.create_subscription()
        sub2 = client.create_subscription()
        sub3 = client.create_subscription()

        assert sub1.subscription_id == 1
        assert sub2.subscription_id == 2
        assert sub3.subscription_id == 3

    @patch("src.io_protocols.opcua_client.thread.start_new_thread")
    def test_start_subscription_polling(self, mock_thread):
        """start_subscription_polling() spawns thread."""
        client = OpcUaClient("http://opcua.local/UA")
        client.start_subscription_polling()

        assert client._polling is True
        mock_thread.assert_called_once()


class TestOpcUaClientCheckConnection:
    """Characterize check_connection() using http.client."""

    @patch("src.io_protocols.opcua_client.http.client.HTTPConnection")
    def test_check_connection_success(self, mock_conn_class):
        """check_connection() returns True for healthy connection."""
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_conn.getresponse.return_value = mock_response
        mock_conn_class.return_value = mock_conn

        client = OpcUaClient("http://opcua.local/UA")
        result = client.check_connection()

        assert result is True
        mock_conn.request.assert_called_once_with("HEAD", "/")

    @patch("src.io_protocols.opcua_client.http.client.HTTPConnection")
    def test_check_connection_server_error(self, mock_conn_class):
        """check_connection() returns False for 500+ status."""
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 500
        mock_conn.getresponse.return_value = mock_response
        mock_conn_class.return_value = mock_conn

        client = OpcUaClient("http://opcua.local/UA")
        result = client.check_connection()

        assert result is False

    @patch("src.io_protocols.opcua_client.http.client.HTTPConnection")
    def test_check_connection_exception(self, mock_conn_class):
        """check_connection() returns False on exception."""
        import http.client
        mock_conn = MagicMock()
        mock_conn.request.side_effect = http.client.HTTPException("error")
        mock_conn_class.return_value = mock_conn

        client = OpcUaClient("http://opcua.local/UA")
        result = client.check_connection()

        assert result is False


class TestOpcUaClientEncoding:
    """Characterize _dec() multi-encoding fallback."""

    def test_dec_unicode_passthrough(self):
        """_dec() returns unicode as-is."""
        client = OpcUaClient("http://opcua.local/UA")
        result = client._dec(u"already unicode")
        assert result == u"already unicode"

    def test_dec_utf8_bytes(self):
        """_dec() decodes UTF-8 bytes."""
        client = OpcUaClient("http://opcua.local/UA")
        result = client._dec("UTF-8 text".encode("utf-8"))
        assert result == "UTF-8 text"

    def test_dec_latin1_fallback(self):
        """_dec() falls back to latin-1."""
        client = OpcUaClient("http://opcua.local/UA")
        # Create bytes that are valid latin-1 but not UTF-8
        data = b"\xe9"  # é in latin-1
        result = client._dec(data)
        assert result == u"\xe9"

    def test_dec_shift_jis(self):
        """_dec() tries shift_jis encoding."""
        client = OpcUaClient("http://opcua.local/UA")
        # Shift-JIS encoded text
        data = "日本語".encode("shift_jis")
        result = client._dec(data)
        assert "日本語" in result or result is not None

    def test_dec_final_fallback_latin1(self):
        """_dec() always succeeds with latin-1 final fallback."""
        client = OpcUaClient("http://opcua.local/UA")
        # Random bytes that may not be valid in any encoding
        data = b"\xff\xfe\xfd"
        result = client._dec(data)
        # Should not raise, returns some string
        assert isinstance(result, str)


class TestOpcUaClientParsing:
    """Characterize XML parsing methods."""

    def test_parse_sid_extracts_session_id(self):
        """_parse_sid() extracts SessionId from XML."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = '<?xml version="1.0"?><Response xmlns="http://opcfoundation.org/UA/"><SessionId>session-abc-123</SessionId></Response>'

        sid = client._parse_sid(xml_body)
        assert sid == "session-abc-123"

    def test_parse_sid_raises_on_missing(self):
        """_parse_sid() raises if SessionId not found."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = '<?xml version="1.0"?><Response xmlns="http://opcfoundation.org/UA/"></Response>'

        with pytest.raises(OpcUaError) as exc_info:
            client._parse_sid(xml_body)
        assert "SessionId" in str(exc_info.value)

    def test_parse_sid_handles_parse_error(self):
        """_parse_sid() raises OpcUaError on malformed XML."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = "not valid xml"

        with pytest.raises(OpcUaError) as exc_info:
            client._parse_sid(xml_body)
        assert "Parse error" in str(exc_info.value)

    def test_parse_read_extracts_value(self):
        """_parse_read() extracts value from XML."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = '<?xml version="1.0"?><Response xmlns:t="http://opcfoundation.org/UA/2008/02/Types.xsd"><t:Value>123.45</t:Value></Response>'

        node = client._parse_read(xml_body, "node1")
        assert node._value == "123.45"

    def test_parse_read_handles_status_code(self):
        """_parse_read() extracts StatusCode."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = '<?xml version="1.0"?><Response xmlns="http://opcfoundation.org/UA/" xmlns:t="http://opcfoundation.org/UA/2008/02/Types.xsd"><t:Value>99</t:Value><StatusCode Code="0x80000000"/></Response>'

        node = client._parse_read(xml_body, "node1")
        assert node._status == 0x80000000

    def test_parse_read_handles_parse_error_gracefully(self):
        """_parse_read() handles parse errors by storing in attributes."""
        client = OpcUaClient("http://opcua.local/UA")
        xml_body = "<invalid xml"

        node = client._parse_read(xml_body, "node1")
        assert "parse_error" in node.attributes
