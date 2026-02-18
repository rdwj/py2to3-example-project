# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/serial_sensor.py

Captures current behavior including:
- struct pack/unpack with binary data
- cStringIO for buffering
- Iterator .next() method (Py2 protocol)
- dict.iteritems(), dict.has_key()
- Sensor packet parsing with bytes/str boundaries
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import struct
import time
from io import StringIO, BytesIO
from unittest import mock

import pytest

from src.io_protocols.serial_sensor import (
    SYNC_BYTE,
    SYNC_ORD,
    SensorPacket,
    SensorPacketStream,
    SerialSensorReader,
)
from src.core.types import DataPoint
from src.core.exceptions import SerialError, ParseError


class MockSerialSource(object):
    """Mock serial port that returns predefined byte sequences."""

    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read(self, n):
        if self._pos >= len(self._data):
            return ""
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


class TestSensorPacket:
    """Test SensorPacket creation and decoding."""

    def test_sensor_packet_creation(self):
        """Test creating a sensor packet with basic fields."""
        payload = struct.pack(">f", 25.5)  # Temperature value as float
        pkt = SensorPacket(0x1234, 0x01, payload, timestamp=1234567890.0)

        assert pkt.sensor_id == 0x1234
        assert pkt.sensor_type == 0x01
        assert pkt.payload == payload
        assert pkt.timestamp == 1234567890.0

    def test_payload_hex(self):
        """Test hex representation of payload."""
        payload = b"\x01\x02\x03\xFF"
        pkt = SensorPacket(0x0001, 0x01, payload)

        hex_repr = pkt.payload_hex()
        assert hex_repr == "01 02 03 FF"

    def test_repr(self):
        """Test string representation."""
        pkt = SensorPacket(0xABCD, 0x02, b"\x00\x01\x02\x03")
        repr_str = repr(pkt)

        assert "0xABCD" in repr_str
        assert "0x02" in repr_str
        assert "4 bytes" in repr_str

    @mock.patch("src.core.types.get_sensor_class")
    def test_decode_with_mock_class(self, mock_get_class):
        """Test decoding payload using sensor class."""
        # Mock sensor class
        mock_reading_class = mock.Mock()
        mock_reading_instance = mock.Mock()
        mock_reading_class.return_value = mock_reading_instance
        mock_get_class.return_value = mock_reading_class

        payload = struct.pack(">f", 100.0)
        pkt = SensorPacket(0x5678, 0x01, payload, timestamp=9999.0)

        result = pkt.decode()

        mock_get_class.assert_called_once_with(0x01)
        mock_reading_class.assert_called_once()
        assert result == mock_reading_instance


class TestSensorPacketStream:
    """Test packet stream iterator."""

    def create_packet_bytes(self, sensor_id, sensor_type, payload):
        """Helper to create valid packet bytes."""
        plen = 2 + 3 + len(payload) + 1  # SYNC + LEN + header + payload + checksum
        body = struct.pack(">HB", sensor_id, sensor_type) + payload

        # Calculate checksum
        chk = SYNC_ORD ^ plen
        for c in body:
            chk ^= ord(c)
        chk &= 0xFF

        packet = SYNC_BYTE + chr(plen) + body + chr(chk)
        return packet

    def test_iterator_protocol(self):
        """Test that stream implements iterator protocol with .next()."""
        payload = struct.pack(">f", 42.0)
        packet_data = self.create_packet_bytes(0x0001, 0x01, payload)

        source = MockSerialSource(packet_data)
        stream = SensorPacketStream(source)

        # Test next() builtin
        pkt = next(stream)
        assert pkt is not None
        assert pkt.sensor_id == 0x0001

    def test_parse_valid_packet(self):
        """Test parsing a valid packet."""
        payload = struct.pack(">f", 123.45)
        packet_data = self.create_packet_bytes(0xABCD, 0x02, payload)

        source = MockSerialSource(packet_data)
        stream = SensorPacketStream(source)

        pkt = next(stream)
        assert pkt.sensor_id == 0xABCD
        assert pkt.sensor_type == 0x02
        assert pkt.payload == payload

    def test_sync_byte_alignment(self):
        """Test skipping to SYNC_BYTE when stream is misaligned."""
        payload = struct.pack(">f", 99.9)
        valid_packet = self.create_packet_bytes(0x1111, 0x01, payload)

        # Prepend garbage bytes before sync
        misaligned_data = b"\xFF\xFE\xFD" + valid_packet

        source = MockSerialSource(misaligned_data)
        stream = SensorPacketStream(source)

        # Should skip garbage and find the packet
        pkt = next(stream)
        assert pkt.sensor_id == 0x1111

    def test_checksum_validation(self):
        """Test checksum validation rejects corrupt packets."""
        payload = struct.pack(">f", 77.7)
        packet_data = self.create_packet_bytes(0x2222, 0x03, payload)

        # Corrupt the checksum byte
        corrupted = packet_data[:-1] + b"\x00"

        source = MockSerialSource(corrupted + b"\x00" * 100)  # pad with zeros
        stream = SensorPacketStream(source, strict=False)

        # Should skip corrupted packet
        # Since there's no valid packet after, should raise StopIteration
        with pytest.raises(StopIteration):
            next(stream)

    def test_checksum_strict_mode_raises(self):
        """Test strict mode raises ParseError on checksum mismatch."""
        payload = struct.pack(">f", 55.5)
        packet_data = self.create_packet_bytes(0x3333, 0x01, payload)

        # Corrupt the checksum
        corrupted = packet_data[:-1] + b"\xFF"

        source = MockSerialSource(corrupted)
        stream = SensorPacketStream(source, strict=True)

        with pytest.raises(ParseError):
            next(stream)

    def test_stop_iteration_on_empty_stream(self):
        """Test StopIteration when stream is exhausted."""
        source = MockSerialSource(b"")
        stream = SensorPacketStream(source)

        with pytest.raises(StopIteration):
            next(stream)


class TestSerialSensorReader:
    """Test the serial sensor reader manager."""

    def test_reader_initialization(self):
        """Test reader initialization with parameters."""
        reader = SerialSensorReader("/dev/ttyS0", baud_rate=19200, timeout=5.0)

        assert reader.port_path == "/dev/ttyS0"
        assert reader.baud_rate == 19200
        assert reader.timeout == 5.0
        assert reader._registry == {}

    def test_register_sensor(self):
        """Test registering sensor metadata."""
        reader = SerialSensorReader("/dev/ttyS0")
        reader.register_sensor(0x1234, "TEMP_SENSOR_01", "Main temperature")

        assert 0x1234 in reader._registry
        assert reader._registry[0x1234]["tag"] == "TEMP_SENSOR_01"
        assert reader._registry[0x1234]["desc"] == "Main temperature"

    def test_dump_registry_uses_iteritems(self, capsys):
        """Test dump_registry uses dict.iteritems()."""
        reader = SerialSensorReader("/dev/ttyS0")
        reader.register_sensor(0x0001, "SENSOR_A")
        reader.register_sensor(0x0002, "SENSOR_B")

        reader.dump_registry()

        captured = capsys.readouterr()
        assert "Registry" in captured.out
        assert "SENSOR_A" in captured.out
        assert "SENSOR_B" in captured.out

    def test_track_uses_has_key(self):
        """Test _track() uses dict.has_key()."""
        reader = SerialSensorReader("/dev/ttyS0")

        # Create a mock packet
        payload = struct.pack(">f", 10.0)
        pkt = SensorPacket(0x9999, 0x01, payload)

        # Track it
        reader._track(pkt)

        # Should auto-create registry entry
        assert 0x9999 in reader._registry
        assert reader._registry[0x9999]["count"] == 1

        # Track again
        reader._track(pkt)
        assert reader._registry[0x9999]["count"] == 2


class TestEncodingBoundaries:
    """Test bytes/str handling at serial boundaries."""

    def test_payload_is_byte_string(self):
        """Test that payload is bytes or str."""
        payload = b"\x41\x42\x43"  # ABC
        pkt = SensorPacket(0x0001, 0x01, payload)

        # In Py3, payload should be bytes or str
        assert isinstance(pkt.payload, (str, bytes))

    def test_sync_byte_is_str(self):
        """Test SYNC_BYTE constant is str (bytes)."""
        assert isinstance(SYNC_BYTE, str)
        assert SYNC_BYTE == "\xAA"

    def test_binary_payload_round_trip(self):
        """Test binary payload with non-ASCII bytes."""
        # Create payload with full byte range
        payload = b"".join(bytes([i]) for i in range(256))

        pkt = SensorPacket(0xFFFF, 0x04, payload)
        assert pkt.payload == payload
