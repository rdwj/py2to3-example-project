# -*- coding: utf-8 -*-
"""
Characterization tests for src/io_protocols/serial_sensor.py

Captures pre-migration behavior of:
- SensorPacket construction, decode, payload_hex with ord()
- SensorPacketStream iterator protocol (.next() method)
- Checksum calculation using ord() on byte characters
- Binary packet parsing with struct.unpack
- cStringIO usage for byte buffering
- SYNC_BYTE as str literal "\\xAA" (byte in Py2, text in Py3)
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import struct
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.io_protocols.serial_sensor import (
    SensorPacket, SensorPacketStream, SerialSensorReader,
    SYNC_BYTE, SYNC_ORD, MIN_PACKET_LEN, MAX_PACKET_LEN,
)
from src.core.exceptions import SerialError, ParseError


# ---------------------------------------------------------------------------
# Helpers -- build valid RS-485 packets
# ---------------------------------------------------------------------------

def build_packet(sensor_id, sensor_type, payload):
    """Build a valid RS-485 packet with correct checksum.

    Format: [SYNC 0xAA] [LEN] [ID_HI] [ID_LO] [TYPE] [PAYLOAD...] [CHK]
    LEN = total packet length including SYNC and LEN bytes.
    CHK = XOR of SYNC ^ LEN ^ all body bytes (excluding CHK itself).
    """
    id_hi = (sensor_id >> 8) & 0xFF
    id_lo = sensor_id & 0xFF
    body = struct.pack("BBB", id_hi, id_lo, sensor_type) + payload
    plen = len(body) + 3  # +3 for SYNC, LEN, CHK
    chk = SYNC_ORD ^ plen
    for b in body:
        chk ^= ord(b)
    chk &= 0xFF
    return chr(SYNC_ORD) + chr(plen) + body + chr(chk)


def build_temp_packet(sensor_id=0x0001, temp_tenths=235):
    """Build a temperature sensor packet (type 0x01, 2 bytes big-endian signed)."""
    payload = struct.pack(">h", temp_tenths)
    return build_packet(sensor_id, 0x01, payload)


def build_pressure_packet(sensor_id=0x0002, pressure_pa=101325):
    """Build a pressure sensor packet (type 0x02, 4 bytes big-endian unsigned)."""
    payload = struct.pack(">I", pressure_pa)
    return build_packet(sensor_id, 0x02, payload)


# ---------------------------------------------------------------------------
# Mock serial port source
# ---------------------------------------------------------------------------

class ByteSource(object):
    """File-like object that returns bytes from a buffer."""
    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read(self, n):
        chunk = self._data[self._pos:self._pos + n]
        self._pos += n
        return chunk


# ---------------------------------------------------------------------------
# SensorPacket
# ---------------------------------------------------------------------------

class TestSensorPacket:
    """Characterize SensorPacket data holder."""

    def test_construction(self):
        """Captures: packet holds sensor_id, type, payload, timestamp."""
        pkt = SensorPacket(0x0001, 0x01, "\x00\xEB", timestamp=1000.0)
        assert pkt.sensor_id == 0x0001
        assert pkt.sensor_type == 0x01
        assert pkt.payload == "\x00\xEB"
        assert pkt.timestamp == 1000.0

    @pytest.mark.py2_behavior
    def test_payload_hex_uses_ord(self):
        """Captures: payload_hex calls ord() on each byte character.
        Py2 str iteration yields single-char strings needing ord().
        Py3 bytes iteration yields ints directly."""
        pkt = SensorPacket(0x0001, 0x01, "\xAA\xBB\xCC")
        hex_str = pkt.payload_hex()
        assert hex_str == "AA BB CC"

    def test_repr(self):
        """Captures: __repr__ format string."""
        pkt = SensorPacket(0x1234, 0x02, "\x00\x01\x00\x02")
        r = repr(pkt)
        assert "0x1234" in r
        assert "0x02" in r
        assert "4 bytes" in r

    def test_as_data_point_unknown_type(self):
        """Captures: unknown sensor type returns DataPoint with value=None, quality=0."""
        pkt = SensorPacket(0x0001, 0xFF, "\x00\x00")
        dp = pkt.as_data_point()
        assert dp.value is None
        assert dp.quality == 0

    @pytest.mark.parametrize("sensor_type,payload,expected_tag", [
        (0x01, struct.pack(">h", 235), "SENSOR_0001"),
        (0x02, struct.pack(">I", 101325), "SENSOR_0002"),
    ])
    def test_decode_known_types(self, sensor_type, payload, expected_tag):
        """Captures: decode dispatches to registered SensorReading subclass."""
        pkt = SensorPacket(int(expected_tag[-4:], 16), sensor_type, payload)
        reading = pkt.decode()
        assert reading is not None
        assert reading.sensor_id == expected_tag


# ---------------------------------------------------------------------------
# SensorPacketStream
# ---------------------------------------------------------------------------

class TestSensorPacketStream:
    """Characterize the packet stream iterator."""

    def test_parse_single_temp_packet(self):
        """Captures: parsing a single valid temperature packet from byte stream."""
        raw = build_temp_packet(0x0001, 235)
        source = ByteSource(raw)
        stream = SensorPacketStream(source)
        pkt = stream.next()
        assert pkt.sensor_id == 0x0001
        assert pkt.sensor_type == 0x01

    def test_parse_multiple_packets(self):
        """Captures: stream yields multiple packets in sequence."""
        raw = build_temp_packet(0x0001, 235) + build_pressure_packet(0x0002, 101325)
        source = ByteSource(raw)
        pkts = list(SensorPacketStream(source))
        assert len(pkts) == 2
        assert pkts[0].sensor_type == 0x01
        assert pkts[1].sensor_type == 0x02

    @pytest.mark.py2_behavior
    def test_iterator_protocol_next_method(self):
        """Captures: Py2 iterator uses .next() method.
        Py3 renamed to __next__()."""
        raw = build_temp_packet()
        source = ByteSource(raw)
        stream = SensorPacketStream(source)
        pkt = stream.next()
        assert pkt is not None

    def test_empty_source_raises_stop_iteration(self):
        """Captures: empty source raises StopIteration from .next()."""
        source = ByteSource("")
        stream = SensorPacketStream(source)
        with pytest.raises(StopIteration):
            stream.next()

    def test_checksum_error_in_strict_mode(self):
        """Captures: bad checksum in strict mode raises ParseError."""
        raw = build_temp_packet(0x0001, 235)
        # Corrupt the checksum (last byte)
        raw = raw[:-1] + chr(ord(raw[-1]) ^ 0xFF)
        source = ByteSource(raw + "\x00")  # extra padding to avoid StopIteration before check
        stream = SensorPacketStream(source, strict=True)
        with pytest.raises(ParseError, match="Checksum mismatch"):
            stream.next()

    def test_checksum_error_non_strict_skips(self):
        """Captures: bad checksum in non-strict mode skips packet."""
        good = build_temp_packet(0x0001, 235)
        bad = build_temp_packet(0x0002, 100)
        bad = bad[:-1] + chr(ord(bad[-1]) ^ 0xFF)  # corrupt checksum
        raw = bad + good
        source = ByteSource(raw)
        stream = SensorPacketStream(source, strict=False)
        pkt = stream.next()
        # Should skip the bad packet and return the good one
        assert pkt.sensor_id == 0x0001

    def test_invalid_length_skipped(self):
        """Captures: packets with length < MIN_PACKET_LEN are skipped."""
        # Build a fake sync + short length
        bad = chr(SYNC_ORD) + chr(2)  # length 2, below minimum
        good = build_temp_packet(0x0001, 235)
        source = ByteSource(bad + good)
        stream = SensorPacketStream(source)
        pkt = stream.next()
        assert pkt.sensor_id == 0x0001


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestSerialSensorEncodingBoundaries:
    """Test binary encoding edge cases in the serial protocol."""

    @pytest.mark.parametrize("byte_val", [0x00, 0x7F, 0x80, 0xFF])
    @pytest.mark.py2_behavior
    def test_ord_on_boundary_bytes(self, byte_val):
        """Captures: ord() on various byte values at encoding boundaries.
        In Py2, ord(chr(x)) == x for all 0-255. Py3 bytes[i] already int."""
        pkt = SensorPacket(0x0001, 0x01, chr(byte_val) + chr(byte_val))
        hex_str = pkt.payload_hex()
        expected = "%02X %02X" % (byte_val, byte_val)
        assert hex_str == expected

    def test_sync_byte_is_str(self):
        """Captures: SYNC_BYTE is a str (byte) literal in Py2.
        After migration, should be bytes b'\\xAA'."""
        assert SYNC_BYTE == "\xAA"
        assert isinstance(SYNC_BYTE, str)

    @pytest.mark.py2_behavior
    def test_packet_with_all_high_bytes(self):
        """Captures: payload containing only high bytes (0x80-0xFF)."""
        payload = "".join(chr(b) for b in range(0x80, 0x88))
        pkt = SensorPacket(0x0001, 0x01, payload)
        hex_str = pkt.payload_hex()
        assert "80" in hex_str
        assert "87" in hex_str
