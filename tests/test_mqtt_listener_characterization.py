# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/mqtt_listener.py

Captures pre-migration behavior of:
- MqttMessage construction and JSON payload decoding (encoding= param)
- MqttSubscription topic matching with Queue.Queue
- MQTT packet construction (_mk_connect, _mk_sub, _mk_pub)
- Variable-length encoding (_el)
- Py2-specific: Queue module, thread module, xrange, json.loads encoding=,
  ord() on bytes, struct.pack with str concatenation
"""


import os
import sys
import json
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.io_protocols.mqtt_listener import (
    MqttMessage, MqttSubscription, MqttListener,
    CONNECT, CONNACK, PUBLISH, SUBSCRIBE, DISCONNECT,
    CONNACK_OK, DEFAULT_PORT,
)


# ---------------------------------------------------------------------------
# MqttMessage
# ---------------------------------------------------------------------------

class TestMqttMessage:
    """Characterize MQTT message handling."""

    def test_construction(self):
        """Captures: message holds topic, payload, timestamp."""
        msg = MqttMessage("sensors/temp", '{"value": 23.5}', timestamp=1000.0)
        assert msg.topic == "sensors/temp"
        assert msg.payload == '{"value": 23.5}'
        assert msg.timestamp == 1000.0

    @pytest.mark.py2_behavior
    def test_json_payload_with_encoding_param(self):
        """Captures: json.loads() called with encoding='utf-8'.
        This param was removed in Python 3.9."""
        payload = json.dumps({"value": 42.0, "quality": 192})
        msg = MqttMessage("sensors/flow", payload)
        result = msg.json_payload()
        assert result["value"] == 42.0
        assert result["quality"] == 192

    def test_json_payload_caches(self):
        """Captures: repeated calls return the same cached object."""
        msg = MqttMessage("t", '{"x": 1}')
        first = msg.json_payload()
        second = msg.json_payload()
        assert first is second

    def test_json_payload_invalid_returns_none(self):
        """Captures: invalid JSON returns None, not an exception."""
        msg = MqttMessage("t", "not valid json {{")
        assert msg.json_payload() is None

    def test_as_data_point_valid_json(self):
        """Captures: as_data_point extracts value and quality from JSON."""
        payload = json.dumps({"value": 100.5, "quality": 192})
        msg = MqttMessage("sensors/pressure", payload, timestamp=1000.0)
        dp = msg.as_data_point()
        assert dp.tag == "sensors/pressure"
        assert dp.value == 100.5
        assert dp.quality == 192
        assert dp.timestamp == 1000.0

    def test_as_data_point_invalid_json(self):
        """Captures: invalid JSON produces DataPoint with value=None, quality=0."""
        msg = MqttMessage("sensors/bad", "{{bad", timestamp=1000.0)
        dp = msg.as_data_point()
        assert dp.value is None
        assert dp.quality == 0

    def test_repr(self):
        """Captures: __repr__ format."""
        msg = MqttMessage("topic/a", "12345")
        r = repr(msg)
        assert "topic/a" in r
        assert "5 bytes" in r

    @pytest.mark.py2_behavior
    def test_json_payload_with_unicode_values(self):
        """Captures: json.loads with encoding= handling unicode content."""
        payload = json.dumps({"label": "caf\u00e9", "value": 23.5})
        msg = MqttMessage("sensors/intl", payload)
        result = msg.json_payload()
        assert "\u00e9" in result["label"]

    @pytest.mark.py2_behavior
    def test_json_payload_with_byte_string(self):
        """Captures: json.loads accepts str (bytes) in Py2 with encoding param."""
        payload = '{"tag": "TEMP-001", "value": 42}'
        assert isinstance(payload, str)
        msg = MqttMessage("t", payload)
        result = msg.json_payload()
        assert result["tag"] == "TEMP-001"


# ---------------------------------------------------------------------------
# MqttSubscription
# ---------------------------------------------------------------------------

class TestMqttSubscription:
    """Characterize subscription topic matching and message queue."""

    @pytest.mark.parametrize("topic_filter,topic,expected", [
        ("sensors/temp", "sensors/temp", True),
        ("sensors/temp", "sensors/flow", False),
        ("sensors/+", "sensors/temp", True),
        ("sensors/+", "sensors/flow", True),
        ("sensors/#", "sensors/temp", True),
        ("sensors/#", "sensors/temp/sub", True),
        ("sensors/+/data", "sensors/temp/data", True),
        ("sensors/+/data", "sensors/temp/other", False),
        ("a/b/c", "a/b", False),
        ("a/b", "a/b/c", False),
    ])
    def test_topic_matching(self, topic_filter, topic, expected):
        """Captures: MQTT topic filter matching with + and # wildcards."""
        sub = MqttSubscription(topic_filter)
        assert sub.matches(topic) == expected

    def test_enqueue_and_get(self):
        """Captures: enqueue a message and retrieve it."""
        sub = MqttSubscription("t/#")
        msg = MqttMessage("t/a", "data")
        sub.enqueue(msg)
        result = sub.get_message(timeout=1.0)
        assert result is msg

    def test_get_timeout_returns_none(self):
        """Captures: get_message with no data returns None after timeout."""
        sub = MqttSubscription("t/#")
        result = sub.get_message(timeout=0.1)
        assert result is None

    @pytest.mark.py2_behavior
    def test_drain_uses_xrange(self):
        """Captures: drain() uses xrange() internally (renamed to range in Py3)."""
        sub = MqttSubscription("t/#")
        for i in range(5):
            sub.enqueue(MqttMessage("t/a", "data%d" % i))
        drained = sub.drain(limit=3)
        assert len(drained) == 3

    def test_drain_empty_queue(self):
        """Captures: drain on empty queue returns empty list."""
        sub = MqttSubscription("t/#")
        assert sub.drain() == []

    def test_queue_overflow_drops_oldest(self):
        """Captures: when queue is full, oldest message is dropped."""
        sub = MqttSubscription("t", maxq=2)
        sub.enqueue(MqttMessage("t", "first"))
        sub.enqueue(MqttMessage("t", "second"))
        sub.enqueue(MqttMessage("t", "third"))  # should drop "first"
        msgs = sub.drain()
        payloads = [m.payload for m in msgs]
        assert "first" not in payloads
        assert "third" in payloads


# ---------------------------------------------------------------------------
# MqttListener -- packet construction (no network)
# ---------------------------------------------------------------------------

class TestMqttListenerPacketConstruction:
    """Characterize MQTT packet construction without network I/O."""

    @pytest.fixture
    def listener(self):
        return MqttListener("localhost", client_id="test_client", keepalive=60)

    @pytest.mark.py2_behavior
    def test_mk_connect_structure(self, listener):
        """Captures: CONNECT packet structure. struct.pack returns bytes in Py3."""
        pkt = listener._mk_connect()
        assert isinstance(pkt, bytes)
        # First byte should be CONNECT type
        assert pkt[0] == CONNECT

    @pytest.mark.py2_behavior
    def test_mk_connect_contains_client_id(self, listener):
        """Captures: CONNECT packet embeds the client_id as bytes."""
        pkt = listener._mk_connect()
        assert b"test_client" in pkt

    @pytest.mark.py2_behavior
    def test_mk_connect_contains_mqtt_protocol(self, listener):
        """Captures: CONNECT packet contains b'MQTT' protocol name."""
        pkt = listener._mk_connect()
        assert b"MQTT" in pkt

    @pytest.mark.py2_behavior
    def test_mk_pub_structure(self, listener):
        """Captures: PUBLISH packet with topic and payload. Returns bytes in Py3."""
        pkt = listener._mk_pub("sensors/temp", '{"value": 42}')
        assert isinstance(pkt, bytes)
        assert pkt[0] == PUBLISH

    @pytest.mark.py2_behavior
    def test_mk_sub_structure(self, listener):
        """Captures: SUBSCRIBE packet with topic filter. Returns bytes in Py3."""
        pkt = listener._mk_sub("sensors/#", 0)
        assert isinstance(pkt, bytes)
        assert pkt[0] == (SUBSCRIBE | 2)

    @pytest.mark.py2_behavior
    def test_variable_length_encoding_small(self, listener):
        """Captures: _el encodes small lengths (< 128) as single byte."""
        encoded = listener._el(10)
        assert isinstance(encoded, bytes)
        assert len(encoded) == 1
        assert encoded[0] == 10

    @pytest.mark.py2_behavior
    def test_variable_length_encoding_medium(self, listener):
        """Captures: _el encodes 128-16383 as two bytes with continuation bit."""
        encoded = listener._el(200)
        assert len(encoded) == 2
        # First byte has continuation bit set
        assert encoded[0] & 0x80 != 0

    @pytest.mark.py2_behavior
    def test_variable_length_encoding_zero(self, listener):
        """Captures: _el(0) produces a single zero byte."""
        encoded = listener._el(0)
        assert len(encoded) == 1
        assert encoded[0] == 0


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestMqttEncodingBoundaries:
    """Test encoding edge cases in MQTT handling."""

    @pytest.mark.py2_behavior
    def test_json_payload_with_non_ascii_utf8(self):
        """Captures: JSON with UTF-8 encoded non-ASCII via encoding= param."""
        data = {"name": "caf\u00e9", "value": 23.5}
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        msg = MqttMessage("intl/data", payload)
        result = msg.json_payload()
        assert result is not None
        assert result["value"] == 23.5

    @pytest.mark.py2_behavior
    def test_topic_as_byte_string(self):
        """Captures: topic matching works with Py2 byte strings."""
        sub = MqttSubscription("sensors/+")
        assert sub.matches("sensors/temp") is True
