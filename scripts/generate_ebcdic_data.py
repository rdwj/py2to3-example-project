#!/usr/bin/env python3
"""
Generator script for sample EBCDIC data file.

This is a Python 3 utility that creates data/sample_ebcdic.dat with
simulated mainframe records encoded in EBCDIC (cp037).  Each record
is 40 bytes:
    - 20 bytes: account name (EBCDIC text, padded with 0x40)
    - 10 bytes: account number (zoned decimal, EBCDIC zones)
    - 8 bytes:  transaction amount (COMP-3 packed decimal)
    - 2 bytes:  record type code (EBCDIC text)

Run once with Python 3 to produce the binary fixture:
    python3 scripts/generate_ebcdic_data.py
"""


import os
import struct

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                           "data", "sample_ebcdic.dat")

EBCDIC_SPACE = 0x40  # EBCDIC space character


def encode_ebcdic_text(text, length):
    """Encode ASCII text to EBCDIC cp037, right-padded with EBCDIC spaces."""
    encoded = text.encode("cp037")
    if len(encoded) > length:
        encoded = encoded[:length]
    return encoded + bytes([EBCDIC_SPACE] * (length - len(encoded)))


def encode_zoned_decimal(number_str, length):
    """Encode a numeric string as EBCDIC zoned decimal.

    Each digit becomes 0xFn (zone 0xF, digit n).  The last byte
    carries sign: 0xCn positive, 0xDn negative.
    """
    negative = number_str.startswith("-")
    digits = number_str.lstrip("-").zfill(length)
    result = bytearray()
    for i, ch in enumerate(digits):
        d = int(ch)
        if i == len(digits) - 1:
            zone = 0xD0 if negative else 0xC0
        else:
            zone = 0xF0
        result.append(zone | d)
    return bytes(result)


def encode_comp3(value, length):
    """Encode an integer as COMP-3 packed decimal.

    Two BCD digits per byte, last nibble is sign (0xC positive, 0xD negative).
    Total length in bytes is specified by `length`.
    """
    negative = value < 0
    digits_str = str(abs(value))
    # Total nibbles available: length * 2, last nibble is sign
    max_digits = length * 2 - 1
    digits_str = digits_str.zfill(max_digits)
    if len(digits_str) > max_digits:
        digits_str = digits_str[:max_digits]

    nibbles = [int(d) for d in digits_str]
    nibbles.append(0x0D if negative else 0x0C)

    result = bytearray()
    for i in range(0, len(nibbles), 2):
        result.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(result)


# Sample records: (account_name, account_number, amount_cents, record_type)
RECORDS = [
    ("ACME MANUFACTURING",  "1234567890",   1523499, "TX"),  # $15,234.99
    ("BERLIN GMBH",         "2345678901",   -87250, "CR"),   # -$872.50
    ("TOKYO HEAVY IND",     "3456789012",  4500000, "TX"),   # $45,000.00
    ("SAO PAULO ENERGIA",   "4567890123",    31075, "TX"),   # $310.75
    ("GREAT LAKES STEEL",   "5678901234", -2199900, "CR"),   # -$21,999.00
]


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "wb") as f:
        for name, acct_no, amount, rec_type in RECORDS:
            name_bytes = encode_ebcdic_text(name, 20)
            acct_bytes = encode_zoned_decimal(acct_no, 10)
            amt_bytes = encode_comp3(amount, 8)
            type_bytes = encode_ebcdic_text(rec_type, 2)

            record = name_bytes + acct_bytes + amt_bytes + type_bytes
            assert len(record) == 40, "Record length %d != 40" % len(record)
            f.write(record)

    print("Wrote %d records (%d bytes) to %s" % (
        len(RECORDS), len(RECORDS) * 40, OUTPUT_PATH))


if __name__ == "__main__":
    main()
