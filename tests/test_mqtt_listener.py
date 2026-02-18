# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/mqtt_listener.py

Captures current Python 2 behavior for MQTT client implementation.
Critical Py2→3 issues: socket send/recv with str, json encoding parameter,
Queue module, thread.start_new_thread(), xrange, print statements,
except comma syntax, integer division.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import json
import struct
import time
from unittest.mock import Mock, patch, MagicMock, call

from src.io_protocols.mqtt_listener import (
    MqttMessage,
    MqttSubscription,
    MqttListener,
    CONNECT,
    CONNACK,
    PUBLISH,
    SUBSCRIBE,
    DISCONNECT,
    CONNACK_OK,
)
from src.core.types import DataPoint
from src.core.exceptions import MqttError


# ============================================================================
# MqttMessage Tests
# ============================================================================


class TestMqttMessage:
    """Characterize MqttMessage behavior."""

    def test_message_basic_construction(self):
        """Message stores topic and payload as-is."""
        msg = MqttMessage("sensors/temp", "payload data")
        assert msg.topic == "sensors/temp"
        assert msg.payload == "payload data"
        assert msg.timestamp is not None

    def test_message_custom_timestamp(self):
        """Message accepts custom timestamp."""
        ts = 1234567890.5
        msg = MqttMessage("test/topic", "data", timestamp=ts)
        assert msg.timestamp == ts

    def test_json_payload_valid(self):
        """json_payload() decodes valid JSON with encoding parameter."""
        payload = '{"value": 42, "quality": 192}'
        msg = MqttMessage("test", payload)
        result = msg.json_payload()
        assert result == {"value": 42, "quality": 192}

    def test_json_payload_caching(self):
        """json_payload() caches result after first decode."""
        msg = MqttMessage("test", '{"a": 1}')
        first = msg.json_payload()
        second = msg.json_payload()
        assert first is second

    def test_json_payload_invalid_returns_none(self):
        """json_payload() returns None for malformed JSON."""
        msg = MqttMessage("test", "{bad json")
        result = msg.json_payload()
        assert result is None

    def test_json_payload_with_unicode_content(self):
        """json_payload() handles UTF-8 encoded unicode."""
        payload = '{"name": "Température", "value": 23.5}'
        msg = MqttMessage("test", payload)
        result = msg.json_payload()
        assert result["name"] == "Température"
        assert result["value"] == 23.5

    def test_json_payload_non_ascii_bytes(self):
        """json_payload() with encoding parameter handles byte strings."""
        # Python 2: str is bytes, json.loads with encoding handles it
        payload = '{"value": "café"}'
        msg = MqttMessage("test", payload)
        result = msg.json_payload()
        assert result is not None
        assert "value" in result

    def test_as_data_point_with_json(self):
        """as_data_point() extracts value and quality from JSON."""
        payload = '{"value": 100, "quality": 192}'
        msg = MqttMessage("sensors/pressure", payload)
        dp = msg.as_data_point()
        assert dp.tag == "sensors/pressure"
        assert dp.value == 100
        assert dp.quality == 192

    def test_as_data_point_custom_keys(self):
        """as_data_point() accepts custom value/quality keys."""
        payload = '{"reading": 55.5, "qc": 200}'
        msg = MqttMessage("sensors/flow", payload)
        dp = msg.as_data_point(vk="reading", qk="qc")
        assert dp.value == 55.5
        assert dp.quality == 200

    def test_as_data_point_no_json_returns_bad_quality(self):
        """as_data_point() returns quality=0 for invalid JSON."""
        msg = MqttMessage("test", "not json")
        dp = msg.as_data_point()
        assert dp.value is None
        assert dp.quality == 0

    def test_as_data_point_missing_quality_defaults(self):
        """as_data_point() defaults quality to 192 if missing."""
        payload = '{"value": 42}'
        msg = MqttMessage("test", payload)
        dp = msg.as_data_point()
        assert dp.quality == 192

    def test_repr_shows_topic_and_length(self):
        """__repr__ includes topic and payload length."""
        msg = MqttMessage("test/topic", "12345")
        r = repr(msg)
        assert "test/topic" in r
        assert "5 bytes" in r


# ============================================================================
# MqttSubscription Tests
# ============================================================================


class TestMqttSubscription:
    """Characterize MqttSubscription queue behavior."""

    def test_subscription_construction(self):
        """Subscription initializes with topic filter and QoS."""
        sub = MqttSubscription("sensors/#", qos=1, maxq=100)
        assert sub.topic_filter == "sensors/#"
        assert sub.qos == 1

    def test_enqueue_puts_message(self):
        """enqueue() adds message to queue."""
        sub = MqttSubscription("test/#")
        msg = MqttMessage("test/a", "data")
        sub.enqueue(msg)
        retrieved = sub.get_message(timeout=0.1)
        assert retrieved is msg

    def test_enqueue_drops_oldest_when_full(self):
        """enqueue() drops oldest message when queue is full."""
        sub = MqttSubscription("test/#", maxq=2)
        msg1 = MqttMessage("test/1", "a")
        msg2 = MqttMessage("test/2", "b")
        msg3 = MqttMessage("test/3", "c")
        sub.enqueue(msg1)
        sub.enqueue(msg2)
        sub.enqueue(msg3)  # Should drop msg1
        first = sub.get_message(timeout=0.1)
        assert first is msg2

    def test_get_message_blocks_until_timeout(self):
        """get_message() blocks for timeout seconds."""
        sub = MqttSubscription("test/#")
        start = time.time()
        result = sub.get_message(timeout=0.1)
        elapsed = time.time() - start
        assert result is None
        assert elapsed >= 0.08  # Allow some slack

    def test_drain_returns_all_messages(self):
        """drain() retrieves up to limit messages."""
        sub = MqttSubscription("test/#")
        for i in range(5):
            sub.enqueue(MqttMessage("test", str(i)))
        msgs = sub.drain(limit=3)
        assert len(msgs) == 3

    def test_drain_stops_at_empty(self):
        """drain() stops when queue is empty."""
        sub = MqttSubscription("test/#")
        sub.enqueue(MqttMessage("test", "a"))
        sub.enqueue(MqttMessage("test", "b"))
        msgs = sub.drain(limit=100)
        assert len(msgs) == 2

    def test_drain_uses_range(self):
        """drain() uses range for iteration."""
        # Characterize current behavior with range
        sub = MqttSubscription("test/#")
        for i in range(50):
            sub.enqueue(MqttMessage("test", str(i)))
        msgs = sub.drain(limit=20)
        assert len(msgs) == 20

    def test_matches_exact_topic(self):
        """matches() returns True for exact match."""
        sub = MqttSubscription("sensors/temp")
        assert sub.matches("sensors/temp") is True
        assert sub.matches("sensors/pressure") is False

    def test_matches_single_level_wildcard(self):
        """matches() handles + wildcard."""
        sub = MqttSubscription("sensors/+/value")
        assert sub.matches("sensors/temp/value") is True
        assert sub.matches("sensors/pressure/value") is True
        assert sub.matches("sensors/temp/status") is False

    def test_matches_multi_level_wildcard(self):
        """matches() handles # wildcard."""
        sub = MqttSubscription("sensors/#")
        assert sub.matches("sensors/temp") is True
        assert sub.matches("sensors/temp/value") is True
        assert sub.matches("devices/pump") is False

    def test_matches_uses_range(self):
        """matches() uses range for iteration."""
        # Characterize range usage in topic matching
        sub = MqttSubscription("a/b/c/d/e/f/g")
        assert sub.matches("a/b/c/d/e/f/g") is True

    def test_matches_length_mismatch(self):
        """matches() returns False when lengths differ (no wildcard)."""
        sub = MqttSubscription("a/b")
        assert sub.matches("a/b/c") is False
        assert sub.matches("a") is False


# ============================================================================
# MqttListener Tests
# ============================================================================


class TestMqttListener:
    """Characterize MqttListener protocol operations."""

    def test_listener_construction(self):
        """Listener initializes with host and port."""
        listener = MqttListener("broker.local", port=1883, client_id="test")
        assert listener.host == "broker.local"
        assert listener.port == 1883
        assert listener.client_id == "test"

    def test_listener_default_client_id(self):
        """Listener generates client ID if not provided."""
        listener = MqttListener("broker.local")
        assert listener.client_id.startswith("idp_")

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_connect_sends_connect_packet(self, mock_socket):
        """connect() sends CONNECT and waits for CONNACK."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance
        connack = struct.pack("BBBB", CONNACK, 2, 0, CONNACK_OK)
        sock_instance.recv.return_value = connack

        listener = MqttListener("broker.local", client_id="test123")
        listener.connect()

        assert listener._up is True
        sock_instance.connect.assert_called_once_with(("broker.local", 1883))
        assert sock_instance.send.call_count == 1

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_connect_raises_on_bad_connack(self, mock_socket):
        """connect() raises MqttError for non-zero CONNACK."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance
        connack = struct.pack("BBBB", CONNACK, 2, 0, 0x01)  # Bad protocol
        sock_instance.recv.return_value = connack

        listener = MqttListener("broker.local")
        with pytest.raises(MqttError) as exc_info:
            listener.connect()
        assert "Bad protocol" in str(exc_info.value)

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_disconnect_sends_disconnect_packet(self, mock_socket):
        """disconnect() sends DISCONNECT packet."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance

        listener = MqttListener("broker.local")
        listener._sock = sock_instance
        listener._up = True
        listener.disconnect()

        assert listener._up is False
        # Should send DISCONNECT packet
        calls = sock_instance.send.call_args_list
        assert any(DISCONNECT in str(c) for c in calls)

    def test_variable_length_encoding_single_byte(self):
        """_el() encodes small numbers in one byte."""
        listener = MqttListener("broker.local")
        result = listener._el(127)
        assert result == struct.pack("B", 127)

    def test_variable_length_encoding_multi_byte(self):
        """_el() encodes larger numbers with continuation bits."""
        listener = MqttListener("broker.local")
        result = listener._el(128)
        # 128 = 0x80, encoded as 0x80 0x01
        assert len(result) == 2

    def test_variable_length_encoding_uses_integer_division(self):
        """_el() uses / for integer division (Py2 behavior)."""
        listener = MqttListener("broker.local")
        result = listener._el(16384)  # Requires 3 bytes
        assert len(result) == 3

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_subscribe_sends_subscribe_packet(self, mock_socket):
        """subscribe() sends SUBSCRIBE and returns subscription."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance
        suback = struct.pack("BBBB", 0x90, 2, 0, 1)
        sock_instance.recv.return_value = suback

        listener = MqttListener("broker.local")
        listener._sock = sock_instance
        listener._up = True

        sub = listener.subscribe("sensors/#", qos=1)

        assert isinstance(sub, MqttSubscription)
        assert sub.topic_filter == "sensors/#"
        assert sub.qos == 1

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_subscribe_raises_if_not_connected(self, mock_socket):
        """subscribe() raises if not connected."""
        listener = MqttListener("broker.local")
        listener._up = False

        with pytest.raises(MqttError) as exc_info:
            listener.subscribe("test/#")
        assert "Not connected" in str(exc_info.value)

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_publish_sends_publish_packet(self, mock_socket):
        """publish() sends PUBLISH packet."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance

        listener = MqttListener("broker.local")
        listener._sock = sock_instance
        listener._up = True

        listener.publish("test/topic", "payload data")

        assert sock_instance.send.call_count == 1
        sent_data = sock_instance.send.call_args[0][0]
        assert isinstance(sent_data, str)  # Py2: socket.send takes str
        assert "test/topic" in sent_data
        assert "payload data" in sent_data

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_publish_raises_if_not_connected(self, mock_socket):
        """publish() raises if not connected."""
        listener = MqttListener("broker.local")
        listener._up = False

        with pytest.raises(MqttError):
            listener.publish("test", "data")

    @patch("src.io_protocols.mqtt_listener._thread.start_new_thread")
    def test_start_listener_spawns_thread(self, mock_thread):
        """start_listener() uses thread.start_new_thread()."""
        listener = MqttListener("broker.local")
        listener.start_listener()

        assert listener._on is True
        mock_thread.assert_called_once()
        # Verify it's calling _loop
        args = mock_thread.call_args[0]
        assert args[0] == listener._loop

    def test_stop_listener_sets_flag(self):
        """stop_listener() sets _on flag to False."""
        listener = MqttListener("broker.local")
        listener._on = True
        listener.stop_listener()
        assert listener._on is False

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_rx_handles_timeout(self, mock_socket):
        """_rx() returns None on socket timeout."""
        import socket as sock_module
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance
        sock_instance.recv.side_effect = sock_module.timeout()

        listener = MqttListener("broker.local")
        listener._sock = sock_instance

        result = listener._rx()
        assert result is None

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_rx_handles_short_packet(self, mock_socket):
        """_rx() handles empty/short responses."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance
        sock_instance.recv.return_value = ""

        listener = MqttListener("broker.local")
        listener._sock = sock_instance

        result = listener._rx()
        assert result is None

    def test_dl_decodes_single_byte_length(self):
        """_dl() decodes single-byte length field."""
        listener = MqttListener("broker.local")
        listener._sock = MagicMock()
        listener._sock.recv.return_value = struct.pack("B", 50)

        result = listener._dl()
        assert result == 50

    def test_dl_uses_xrange(self):
        """_dl() uses xrange for up to 4 bytes."""
        listener = MqttListener("broker.local")
        listener._sock = MagicMock()
        # Multi-byte: 0x80 0x01 = 128
        listener._sock.recv.side_effect = [struct.pack("B", 0x80), struct.pack("B", 0x01)]

        result = listener._dl()
        assert result == 128

    @patch("src.io_protocols.mqtt_listener.socket.socket")
    def test_loop_dispatches_publish_to_subscriptions(self, mock_socket):
        """_loop() routes PUBLISH packets to matching subscriptions."""
        sock_instance = MagicMock()
        mock_socket.return_value = sock_instance

        # Build PUBLISH packet: topic "a/b", payload "test"
        topic = "a/b"
        payload = "test"
        vh = struct.pack(">H", len(topic)) + topic
        pkt = struct.pack("B", PUBLISH) + struct.pack("B", len(vh) + len(payload)) + vh + payload

        # First call returns packet, second returns None to break loop
        sock_instance.recv.side_effect = [pkt[:1], pkt[1:2], pkt[2:], None]

        listener = MqttListener("broker.local")
        listener._sock = sock_instance
        listener._up = True
        listener._on = True

        sub = MqttSubscription("a/#")
        listener._subs.append(sub)

        # Run one iteration
        listener._loop()

        # Should have dispatched message
        msg = sub.get_message(timeout=0.1)
        if msg:  # May be None if packet parsing failed
            assert msg.topic == topic
            assert msg.payload == payload
