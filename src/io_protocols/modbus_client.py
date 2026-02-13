# -*- coding: utf-8 -*-
"""
MODBUS TCP/RTU client for the Legacy Industrial Data Platform.
Reads holding registers from SCADA PLCs over TCP sockets.
"""
import socket
import struct
import time
import thread

from src.core.types import DataPoint, register_view
from src.core.exceptions import ModbusError

FC_READ_HOLDING_REGISTERS   = 0x03
FC_READ_INPUT_REGISTERS     = 0x04
FC_WRITE_SINGLE_REGISTER    = 0x06
FC_WRITE_MULTIPLE_REGISTERS = 0x10

MODBUS_EXCEPTIONS = {
    0x01: "Illegal function", 0x02: "Illegal data address",
    0x03: "Illegal data value", 0x04: "Slave device failure",
    0x06: "Slave device busy",
}
_CRC16_POLY = 0xA001
_FRAME_DELIM = b"|"
DEFAULT_TIMEOUT = 5.0
DEFAULT_PORT = 502


def crc16_modbus(data):
    """CRC-16 for MODBUS RTU.  Uses integer division (/) not floor
    division (//) -- Py2 truncation is correct for positive ints."""
    crc = 0xFFFF
    for byte_val in data:
        if isinstance(byte_val, str):
            byte_val = ord(byte_val)
        crc = crc ^ byte_val
        for _ in xrange(8):
            if crc & 0x0001:
                crc = (crc / 2) ^ _CRC16_POLY
            else:
                crc = crc / 2
    return crc & 0xFFFF


class ModbusFrame(object):
    """MODBUS TCP ADU -- MBAP header plus PDU."""
    _transaction_counter = 0

    def __init__(self, unit_id, function_code, payload=""):
        ModbusFrame._transaction_counter += 1
        self.transaction_id = ModbusFrame._transaction_counter & 0xFFFF
        self.unit_id = unit_id
        self.function_code = function_code
        self.payload = payload

    def to_tcp_adu(self):
        pdu = struct.pack("B", self.function_code) + self.payload
        header = struct.pack(">HHHB", self.transaction_id, 0x0000,
                             len(pdu) + 1, self.unit_id)
        return header + pdu

    def to_rtu_frame(self):
        body = struct.pack("BB", self.unit_id, self.function_code) + self.payload
        return body + struct.pack("<H", crc16_modbus(body))

    @staticmethod
    def build_read_holding(unit_id, start_addr, quantity):
        return ModbusFrame(unit_id, FC_READ_HOLDING_REGISTERS,
                           struct.pack(">HH", start_addr, quantity))

    @staticmethod
    def build_write_single(unit_id, address, value):
        return ModbusFrame(unit_id, FC_WRITE_SINGLE_REGISTER,
                           struct.pack(">HH", address, value))

    def __repr__(self):
        return "ModbusFrame(txn=%d, unit=%d, fc=0x%02X, %d bytes)" % (
            self.transaction_id, self.unit_id,
            self.function_code, len(self.payload))


class RegisterBank(object):
    """In-memory cache of PLC holding registers with zero-copy views."""

    def __init__(self, base_address, raw_data):
        self.base_address = base_address
        self._raw = raw_data
        self._count = len(raw_data) / 2  # integer division, 2 bytes per reg

    def get_register(self, address):
        offset = (address - self.base_address) * 2
        if offset < 0 or offset + 2 > len(self._raw):
            raise ModbusError("Register %d out of range" % address,
                              function_code=FC_READ_HOLDING_REGISTERS)
        return struct.unpack(">H", self._raw[offset:offset + 2])[0]

    def get_register_view(self, start_addr, count):
        """Zero-copy view via buffer() -- becomes memoryview() in Py3."""
        offset = (start_addr - self.base_address) * 2
        return buffer(self._raw, offset, count * 2)

    def get_float32(self, address):
        offset = (address - self.base_address) * 2
        return struct.unpack(">f", self._raw[offset:offset + 4])[0]

    def __repr__(self):
        return "RegisterBank(base=%d, count=%d)" % (
            self.base_address, self._count)


class ModbusClient(object):
    """MODBUS TCP client with persistent connection and background polling."""

    def __init__(self, host, port=DEFAULT_PORT, unit_id=1, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._sock = None
        self._lock = thread.allocate_lock()
        self._connected = False
        self._poll_active = False

    def connect(self):
        print "MODBUS: connecting to %s:%d unit %d" % (self.host, self.port, self.unit_id)
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            self._connected = True
            print "MODBUS: connected"
        except socket.error, e:
            raise ModbusError("Connection failed: %s" % e)

    def disconnect(self):
        self._poll_active = False
        if self._sock:
            try:
                self._sock.close()
            except socket.error, e:
                print "MODBUS: disconnect warning -- %s" % e
            self._sock = None
            self._connected = False

    def read_holding_registers(self, start_addr, quantity):
        """Read holding registers.  Socket recv() returns str in Py2."""
        frame = ModbusFrame.build_read_holding(self.unit_id, start_addr, quantity)
        response = self._transact(frame)
        if len(response) < 2:
            raise ModbusError("Truncated response")
        resp_fc = ord(response[0])
        if resp_fc & 0x80:
            exc = ord(response[1])
            raise ModbusError("Slave exception: %s" % MODBUS_EXCEPTIONS.get(exc, "Unknown"),
                              function_code=resp_fc & 0x7F, exception_code=exc)
        byte_count = ord(response[1])
        print "MODBUS: read %d regs at %d" % (quantity, start_addr)
        return RegisterBank(start_addr, response[2:2 + byte_count])

    def write_single_register(self, address, value):
        frame = ModbusFrame.build_write_single(self.unit_id, address, value)
        response = self._transact(frame)
        if ord(response[0]) & 0x80:
            exc = ord(response[1])
            raise ModbusError("Write failed: %s" % MODBUS_EXCEPTIONS.get(exc, "Unknown"),
                              function_code=ord(response[0]) & 0x7F, exception_code=exc)
        print "MODBUS: wrote %d to reg %d" % (value, address)

    def start_polling(self, address, quantity, interval_sec, callback):
        """Background poll via thread.start_new_thread()."""
        self._poll_active = True
        thread.start_new_thread(self._poll_loop, (address, quantity, interval_sec, callback))

    def stop_polling(self):
        self._poll_active = False

    def _transact(self, frame):
        if not self._connected:
            raise ModbusError("Not connected")
        self._lock.acquire()
        try:
            self._sock.send(frame.to_tcp_adu())
            hdr = self._recv_exact(7)
            if len(hdr) < 7:
                raise ModbusError("Incomplete MBAP header")
            _txn, _proto, length, _unit = struct.unpack(">HHHB", hdr)
            return self._recv_exact(length - 1)
        except socket.timeout, e:
            raise ModbusError("Timeout from %s:%d" % (self.host, self.port))
        except socket.error, e:
            self._connected = False
            raise ModbusError("Socket error: %s" % e)
        finally:
            self._lock.release()

    def _recv_exact(self, n):
        chunks = []
        got = 0
        while got < n:
            chunk = self._sock.recv(n - got)
            if not chunk:
                break
            chunks.append(chunk)
            got += len(chunk)
        return "".join(chunks)

    def _poll_loop(self, address, quantity, interval_sec, callback):
        while self._poll_active:
            try:
                bank = self.read_holding_registers(address, quantity)
                points = []
                for i in xrange(quantity):
                    addr = address + i
                    tag = "PLC_%s_%d" % (self.host.replace(".", "_"), addr)
                    points.append(DataPoint(tag, bank.get_register(addr)))
                callback(points)
            except ModbusError, e:
                print "MODBUS: poll error -- %s" % e
            time.sleep(interval_sec)
