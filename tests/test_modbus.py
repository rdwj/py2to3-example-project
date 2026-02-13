# -*- coding: utf-8 -*-
"""
Tests for the MODBUS TCP/RTU client: CRC-16 calculation, frame
construction, RegisterBank with integer division, struct pack/unpack.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.io_protocols.modbus_client import (
    crc16_modbus, ModbusFrame, RegisterBank,
    FC_READ_HOLDING_REGISTERS, FC_WRITE_SINGLE_REGISTER,
)
from src.core.exceptions import ModbusError


class TestCrc16Modbus(unittest.TestCase):

    def test_empty_input(self):
        crc = crc16_modbus(b"")
        self.assertEqual(crc, 0xFFFF)
        print("CRC empty: 0x%04X" % crc)

    def test_deterministic(self):
        data = b"\x01\x03\x00\x00\x00\x0A"
        self.assertEqual(crc16_modbus(data), crc16_modbus(data))

    def test_different_data_different_crc(self):
        a = crc16_modbus(b"\x01\x02\x03")
        b = crc16_modbus(b"\x04\x05\x06")
        self.assertNotEqual(a, b)
        print("CRC differs: 0x%04X vs 0x%04X" % (a, b))

    def test_result_is_16bit(self):
        crc = crc16_modbus(b"\xFF\xAA\x55")
        self.assertTrue(0 <= crc <= 0xFFFF)


class TestModbusFrame(unittest.TestCase):

    def test_tcp_adu_structure(self):
        frame = ModbusFrame(1, 0x03, b"\x00\x00\x00\x0A")
        adu = frame.to_tcp_adu()
        self.assertIsInstance(adu, bytes)
        txn, proto, length, unit = struct.unpack(">HHHB", adu[:7])
        self.assertEqual(proto, 0x0000)
        self.assertEqual(unit, 1)
        self.assertEqual(length, 1 + 1 + 4)
        print("TCP ADU: %d bytes, txn=%d" % (len(adu), txn))

    def test_rtu_frame_crc(self):
        frame = ModbusFrame(1, 0x03, b"\x00\x00\x00\x01")
        rtu = frame.to_rtu_frame()
        body, crc_bytes = rtu[:-2], rtu[-2:]
        expected = crc16_modbus(body)
        actual = struct.unpack("<H", crc_bytes)[0]
        self.assertEqual(actual, expected)
        print("RTU CRC verified: 0x%04X" % actual)

    def test_build_read_holding(self):
        frame = ModbusFrame.build_read_holding(2, 100, 10)
        self.assertEqual(frame.function_code, FC_READ_HOLDING_REGISTERS)
        start, qty = struct.unpack(">HH", frame.payload)
        self.assertEqual(start, 100)
        self.assertEqual(qty, 10)

    def test_build_write_single(self):
        frame = ModbusFrame.build_write_single(1, 40001, 12345)
        self.assertEqual(frame.function_code, FC_WRITE_SINGLE_REGISTER)
        addr, val = struct.unpack(">HH", frame.payload)
        self.assertEqual(addr, 40001)
        self.assertEqual(val, 12345)

    def test_transaction_ids_increment(self):
        f1 = ModbusFrame(1, 0x03)
        f2 = ModbusFrame(1, 0x03)
        self.assertEqual(f2.transaction_id, f1.transaction_id + 1)


class TestRegisterBank(unittest.TestCase):

    def test_count_uses_integer_division(self):
        bank = RegisterBank(0, b"\x00" * 10)
        self.assertEqual(bank._count, 5)
        print("Register count: %d" % bank._count)

    def test_odd_bytes_truncate(self):
        bank = RegisterBank(0, b"\x00" * 11)
        self.assertEqual(bank._count, 5)  # 11 / 2 = 5

    def test_get_register(self):
        raw = struct.pack(">HHH", 0x0100, 0x0200, 0x0300)
        bank = RegisterBank(10, raw)
        self.assertEqual(bank.get_register(10), 0x0100)
        self.assertEqual(bank.get_register(12), 0x0300)

    def test_out_of_range_raises(self):
        bank = RegisterBank(0, struct.pack(">HH", 1, 2))
        self.assertRaises(ModbusError, bank.get_register, 99)

    def test_get_float32(self):
        raw = struct.pack(">f", 3.14)
        bank = RegisterBank(0, raw)
        self.assertAlmostEqual(bank.get_float32(0), 3.14, places=2)

    def test_get_register_view(self):
        raw = b"\x00\x01\x00\x02\x00\x03\x00\x04"
        bank = RegisterBank(0, raw)
        view = bank.get_register_view(1, 2)
        self.assertEqual(len(view), 4)
        self.assertEqual(bytes(view), b"\x00\x02\x00\x03")


if __name__ == "__main__":
    unittest.main()
