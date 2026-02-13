# -*- coding: utf-8 -*-
"""
RS-485 serial sensor reader for the Legacy Industrial Data Platform.
Packet format: [SYNC 0xAA] [LEN] [ID_HI] [ID_LO] [TYPE] [PAYLOAD...] [CHK]
"""
import struct
import time
from cStringIO import StringIO

from src.core.types import DataPoint, SensorReading, get_sensor_class
from src.core.exceptions import SerialError, ParseError

SYNC_BYTE = "\xAA"
SYNC_ORD  = 0xAA
MIN_PACKET_LEN = 6
MAX_PACKET_LEN = 256
_TYPE_NAMES = {0x01: "Temperature", 0x02: "Pressure",
               0x03: "Flow", 0x04: "Vibration"}


class SensorPacket(object):
    """Validated RS-485 sensor packet.  Payload is str (byte string)
    -- what the serial port returns in Python 2."""

    def __init__(self, sensor_id, sensor_type, payload, timestamp=None):
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.payload = payload
        self.timestamp = timestamp or time.time()
        self._reading = None

    def decode(self):
        """Decode via struct.unpack with str format args."""
        if self._reading is not None:
            return self._reading
        try:
            cls = get_sensor_class(self.sensor_type)
            self._reading = cls("SENSOR_%04X" % self.sensor_id,
                                self.payload, self.timestamp)
            return self._reading
        except KeyError:
            print "SERIAL: unknown type 0x%02X sensor %04X" % (
                self.sensor_type, self.sensor_id)
            return None

    def as_data_point(self):
        r = self.decode()
        if r is not None:
            return r.as_data_point()
        return DataPoint("SENSOR_%04X" % self.sensor_id, None,
                         self.timestamp, quality=0)

    def payload_hex(self):
        return " ".join("%02X" % ord(b) for b in self.payload)

    def __repr__(self):
        return "SensorPacket(0x%04X, type=0x%02X, %d bytes)" % (
            self.sensor_id, self.sensor_type, len(self.payload))


class SensorPacketStream(object):
    """Iterator yielding SensorPackets from a raw byte source.
    Uses .next() method (Py2 iterator protocol; Py3 uses __next__)."""

    def __init__(self, source, strict=False):
        self._source = source
        self._strict = strict
        self._buf = StringIO()
        self._read = 0
        self._errors = 0

    def __iter__(self):
        return self

    def next(self):
        while True:
            b = self._source.read(1)
            if not b:
                raise StopIteration
            if b != SYNC_BYTE:
                continue
            lb = self._source.read(1)
            if not lb:
                raise StopIteration
            plen = ord(lb)
            if plen < MIN_PACKET_LEN or plen > MAX_PACKET_LEN:
                self._errors += 1
                continue
            body = self._source.read(plen - 2)
            if len(body) < plen - 2:
                raise StopIteration
            sid, stype = struct.unpack(">HB", body[:3])
            payload, rxchk = body[3:-1], ord(body[-1])
            chk = SYNC_ORD ^ plen
            for c in body[:-1]:
                chk ^= ord(c)
            chk &= 0xFF
            if chk != rxchk:
                self._errors += 1
                if self._strict:
                    raise ParseError("Checksum mismatch sensor 0x%04X: "
                                     "exp 0x%02X got 0x%02X" % (sid, chk, rxchk))
                print "SERIAL: chksum error 0x%04X (exp %02X got %02X)" % (
                    sid, chk, rxchk)
                continue
            self._read += 1
            print "SERIAL: pkt #%d sensor 0x%04X (%s) %d bytes" % (
                self._read, sid, _TYPE_NAMES.get(stype, "?"), len(payload))
            return SensorPacket(sid, stype, payload)


class SerialSensorReader(object):
    """Manages RS-485 serial port and sensor registry."""

    def __init__(self, port_path, baud_rate=9600, timeout=2.0):
        self.port_path = port_path
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._port = None
        self._registry = {}
        self._running = False

    def open(self):
        """Open serial port.  Returns raw str in Py2 -- no encoding."""
        print "SERIAL: opening %s at %d baud" % (self.port_path, self.baud_rate)
        try:
            self._port = open(self.port_path, "rb")
        except IOError, e:
            raise SerialError("Failed to open %s: %s" % (self.port_path, e))

    def close(self):
        self._running = False
        if self._port:
            self._port.close()
            self._port = None

    def register_sensor(self, sid, tag, desc=""):
        self._registry[sid] = {"tag": tag, "desc": desc,
                                "last": None, "count": 0}

    def read_one_packet(self):
        if not self._port:
            raise SerialError("Port not open")
        pkt = SensorPacketStream(self._port).next()
        self._track(pkt)
        return pkt

    def stream_packets(self, max_packets=None):
        if not self._port:
            raise SerialError("Port not open")
        self._running = True
        n = 0
        for pkt in SensorPacketStream(self._port):
            if not self._running:
                break
            self._track(pkt)
            n += 1
            if n % 100 == 0:
                self._log_summary()
            yield pkt
            if max_packets and n >= max_packets:
                break

    def dump_registry(self):
        """Uses dict.iteritems() -- lazy in Py2, removed in Py3."""
        print "SERIAL: --- Registry ---"
        for sid, info in self._registry.iteritems():
            print "  0x%04X: tag=%s n=%d" % (sid, info["tag"], info["count"])

    def _track(self, pkt):
        sid = pkt.sensor_id
        if not self._registry.has_key(sid):
            self._registry[sid] = {"tag": "SENSOR_%04X" % sid,
                                    "desc": "auto", "last": None, "count": 0}
        self._registry[sid]["last"] = pkt
        self._registry[sid]["count"] += 1

    def _log_summary(self):
        total = 0
        for sid, info in self._registry.iteritems():
            total += info["count"]
        print "SERIAL: %d sensors, %d reads" % (len(self._registry), total)
