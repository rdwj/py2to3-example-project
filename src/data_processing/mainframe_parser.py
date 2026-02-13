# -*- coding: utf-8 -*-
"""
Mainframe batch file parser for the Legacy Industrial Data Platform.

Handles nightly data transfers from the IBM z/OS mainframe that runs the
corporate ERP system.  Records arrive as fixed-width EBCDIC-encoded flat
files whose layouts are defined by COBOL copybooks.  Account numbers and
transaction amounts use COMP-3 packed decimal encoding; the remaining
fields are character data padded with EBCDIC spaces (0x40).

The mainframe job ERPX400 transmits via Connect:Direct every night at
02:00 UTC.  Files land in /opt/platform/incoming/mainframe/ and are
picked up by the batch scheduler.
"""

import os
import struct
import codecs
import time
import cPickle

from core.types import LargeCounter
from core.exceptions import ParseError, DataError
from core.config_loader import load_platform_config


# ---------------------------------------------------------------------------
# EBCDIC codec registration
# ---------------------------------------------------------------------------

# IBM EBCDIC codepage 037 (US/Canada) -- the mainframe uses this for
# all character fields.  Python ships cp037 in its codec library.
EBCDIC_CODEC = "cp037"

# Packed-decimal sign nibble values
_COMP3_POSITIVE = (0x0C, 0x0A, 0x0E, 0x0F)
_COMP3_NEGATIVE = (0x0D, 0x0B)

# Output file permissions -- the batch scheduler runs as a service
# account and the reporting subsystem needs group read access.
OUTPUT_FILE_MODE = 0755

# Maximum record length we will accept before assuming corruption
MAX_RECORD_LENGTH = 32768


# ---------------------------------------------------------------------------
# CopybookLayout -- describes the fixed-width field positions in a record
# ---------------------------------------------------------------------------

class CopybookLayout(object):
    """Describes the fixed-width field positions from a COBOL copybook.

    Each field is a tuple of (name, start_offset, length, field_type)
    where field_type is one of 'char', 'comp3', 'binary', 'zoned'.
    Offsets are zero-based byte positions in the EBCDIC record.
    """

    FIELD_CHAR = "char"
    FIELD_COMP3 = "comp3"
    FIELD_BINARY = "binary"
    FIELD_ZONED = "zoned"

    def __init__(self, layout_name, record_length):
        self.layout_name = layout_name
        self.record_length = record_length
        self._fields = []
        self._field_index = {}

    def add_field(self, name, offset, length, field_type="char", decimal_places=0):
        """Register a field in the copybook layout."""
        field_def = {
            "name": name,
            "offset": offset,
            "length": length,
            "type": field_type,
            "decimal_places": decimal_places,
        }
        self._fields.append(field_def)
        self._field_index[name] = field_def

    def get_field(self, name):
        """Look up a field definition by name."""
        if not self._field_index.has_key(name):
            raise ParseError("Unknown field '%s' in layout '%s'" % (name, self.layout_name))
        return self._field_index[name]

    def field_names(self):
        return [f["name"] for f in self._fields]

    def iter_fields(self):
        return iter(self._fields)

    def __repr__(self):
        return "CopybookLayout(%r, reclen=%d, fields=%d)" % (
            self.layout_name, self.record_length, len(self._fields),
        )


# ---------------------------------------------------------------------------
# MainframeRecord -- a single parsed record
# ---------------------------------------------------------------------------

class MainframeRecord(object):
    """A single record extracted from a mainframe batch file."""

    def __init__(self, record_number, raw_bytes, layout):
        self.record_number = record_number
        self.raw_bytes = raw_bytes
        self.layout = layout
        self._parsed_fields = {}
        self._parse_errors = []

    def get(self, field_name, default=None):
        if self._parsed_fields.has_key(field_name):
            return self._parsed_fields[field_name]
        return default

    def set_field(self, field_name, value):
        self._parsed_fields[field_name] = value

    def has_errors(self):
        return len(self._parse_errors) > 0

    def errors(self):
        return list(self._parse_errors)

    def add_error(self, message):
        self._parse_errors.append(message)

    def as_dict(self):
        return dict(self._parsed_fields)

    def __repr__(self):
        return "MainframeRecord(#%d, fields=%d, errors=%d)" % (
            self.record_number, len(self._parsed_fields), len(self._parse_errors),
        )


# ---------------------------------------------------------------------------
# COMP-3 packed decimal decoding
# ---------------------------------------------------------------------------

def decode_comp3(raw_bytes):
    """Decode a COBOL COMP-3 (packed decimal) field from raw bytes.

    Packed decimal stores two digits per byte in BCD, with the low
    nibble of the last byte holding the sign.  For example, the value
    +12345 is stored as bytes 0x01 0x23 0x45 0x3C (three data bytes
    plus sign nibble C = positive).
    """
    if not raw_bytes:
        raise ParseError("Empty COMP-3 field")

    result = 0L
    byte_array = [ord(b) for b in raw_bytes]

    # Process all bytes except the last -- each byte has two BCD digits
    for i in xrange(len(byte_array) - 1):
        high_nibble = (byte_array[i] >> 4) & 0x0F
        low_nibble = byte_array[i] & 0x0F
        result = result * 100L + long(high_nibble * 10 + low_nibble)

    # Last byte: high nibble is the final digit, low nibble is the sign
    last_byte = byte_array[-1]
    final_digit = (last_byte >> 4) & 0x0F
    sign_nibble = last_byte & 0x0F
    result = result * 10L + long(final_digit)

    if sign_nibble in _COMP3_NEGATIVE:
        result = -result

    return result


def decode_binary_field(raw_bytes, signed=True):
    """Decode a COBOL BINARY (COMP) field using struct.

    The mainframe uses big-endian byte order.  Field widths of 2, 4,
    and 8 bytes correspond to COMP PIC S9(4), S9(9), and S9(18).
    """
    length = len(raw_bytes)
    if length == 2:
        fmt = ">h" if signed else ">H"
    elif length == 4:
        fmt = ">i" if signed else ">I"
    elif length == 8:
        fmt = ">q" if signed else ">Q"
    else:
        raise ParseError("Unsupported BINARY field length: %d bytes" % length)
    return struct.unpack(fmt, raw_bytes)[0]


def decode_zoned_decimal(raw_bytes):
    """Decode a zoned decimal (DISPLAY numeric) field from EBCDIC.

    Each byte contains a digit in the low nibble; the high nibble is
    the zone (0xF for digits, 0xC/0xD for the sign on the last byte).
    """
    if not raw_bytes:
        return 0L

    result = 0L
    byte_array = [ord(b) for b in raw_bytes]

    for i in xrange(len(byte_array) - 1):
        digit = byte_array[i] & 0x0F
        result = result * 10L + long(digit)

    # Last byte carries the sign in the zone nibble
    last_byte = byte_array[-1]
    digit = last_byte & 0x0F
    zone = (last_byte >> 4) & 0x0F
    result = result * 10L + long(digit)

    if zone == 0x0D:
        result = -result

    return result


# ---------------------------------------------------------------------------
# MainframeParser -- orchestrates the parsing of a batch file
# ---------------------------------------------------------------------------

class MainframeParser(object):
    """Parse mainframe batch files using a COBOL copybook layout definition.

    Usage::

        layout = CopybookLayout("ERPX400-TRANS", 250)
        layout.add_field("ACCOUNT-NO", 0, 6, "comp3")
        layout.add_field("CUST-NAME", 6, 40, "char")
        layout.add_field("TRANS-AMT", 46, 5, "comp3", decimal_places=2)

        parser = MainframeParser(layout)
        records = parser.parse_file("/opt/platform/incoming/mainframe/TRANS.20240115.dat")
    """

    # Account number mask for routing -- high 4 bits encode the region
    ACCOUNT_REGION_MASK = 0xFFFFFFFFL

    def __init__(self, layout, cache_dir=None):
        self._layout = layout
        self._cache_dir = cache_dir
        self._record_count = LargeCounter(0L)
        self._error_count = LargeCounter(0L)
        self._config = load_platform_config()

    def parse_file(self, file_path):
        """Parse all records from a mainframe batch file.

        Uses the ``file()`` builtin to open in binary mode.  The file is
        read as raw bytes, then each record is sliced according to the
        copybook layout and decoded from EBCDIC.
        """
        # Check for a cached parse result first
        cached = self._load_cache(file_path)
        if cached is not None:
            print "Loaded %d cached records for %s" % (len(cached), file_path)
            return cached

        print "Parsing mainframe file: %s" % file_path
        start_time = time.time()
        records = []

        f = file(file_path, "rb")
        try:
            record_num = 0
            while True:
                raw = f.read(self._layout.record_length)
                if not raw:
                    break
                if len(raw) < self._layout.record_length:
                    print "WARNING: Truncated record #%d (%d bytes, expected %d)" % (
                        record_num, len(raw), self._layout.record_length,
                    )
                    self._error_count.increment()
                    break

                record = self._parse_record(record_num, raw)
                records.append(record)
                record_num += 1
                self._record_count.increment()

                if record_num % 10000 == 0:
                    print "  ... parsed %d records" % record_num
        finally:
            f.close()

        elapsed = time.time() - start_time
        print "Parsed %d records in %.2f seconds (%d errors)" % (
            len(records), elapsed, long(self._error_count.value),
        )

        self._save_cache(file_path, records)
        self._write_summary(file_path, records)

        return records

    def _parse_record(self, record_num, raw_bytes):
        """Parse a single fixed-width record according to the copybook layout."""
        record = MainframeRecord(record_num, raw_bytes, self._layout)

        for field_def in self._layout.iter_fields():
            name = field_def["name"]
            offset = field_def["offset"]
            length = field_def["length"]
            ftype = field_def["type"]
            decimals = field_def["decimal_places"]

            # Fixed-width byte slicing -- str is bytes in Python 2 so
            # this extracts a byte substring directly
            field_bytes = raw_bytes[offset:offset + length]

            try:
                if ftype == CopybookLayout.FIELD_CHAR:
                    # Decode EBCDIC character data to unicode
                    value = field_bytes.decode(EBCDIC_CODEC).rstrip()
                elif ftype == CopybookLayout.FIELD_COMP3:
                    raw_value = decode_comp3(field_bytes)
                    if decimals > 0:
                        value = float(raw_value) / (10 ** decimals)
                    else:
                        value = long(raw_value)
                elif ftype == CopybookLayout.FIELD_BINARY:
                    value = decode_binary_field(field_bytes)
                elif ftype == CopybookLayout.FIELD_ZONED:
                    raw_value = decode_zoned_decimal(field_bytes)
                    if decimals > 0:
                        value = float(raw_value) / (10 ** decimals)
                    else:
                        value = long(raw_value)
                else:
                    value = field_bytes
                    record.add_error("Unknown field type '%s' for %s" % (ftype, name))

                record.set_field(name, value)

            except Exception, e:
                record.add_error("Error parsing field %s: %s" % (name, str(e)))
                self._error_count.increment()

        # Post-parse: mask account numbers for region routing
        account_raw = record.get("ACCOUNT-NO")
        if account_raw is not None and isinstance(account_raw, (int, long)):
            region_code = long(account_raw) & self.ACCOUNT_REGION_MASK
            record.set_field("_REGION_CODE", region_code)

        return record

    # ---------------------------------------------------------------
    # Cache management -- cPickle for fast serialization
    # ---------------------------------------------------------------

    def _cache_key(self, file_path):
        """Generate a cache key from the file path and modification time."""
        stat = os.stat(file_path)
        return "%s_%d_%d" % (
            os.path.basename(file_path), stat.st_size, int(stat.st_mtime),
        )

    def _cache_path(self, file_path):
        if self._cache_dir is None:
            return None
        return os.path.join(self._cache_dir, self._cache_key(file_path) + ".cache")

    def _load_cache(self, file_path):
        """Attempt to load a previously parsed result from the cache."""
        cache_file = self._cache_path(file_path)
        if cache_file is None or not os.path.exists(cache_file):
            return None
        try:
            f = file(cache_file, "rb")
            try:
                data = cPickle.load(f)
            finally:
                f.close()
            return data
        except (cPickle.UnpicklingError, IOError, EOFError), e:
            print "Cache read failed for %s: %s" % (file_path, str(e))
            return None

    def _save_cache(self, file_path, records):
        """Write parsed records to the cache directory for future runs."""
        cache_file = self._cache_path(file_path)
        if cache_file is None:
            return
        try:
            f = file(cache_file, "wb")
            try:
                cPickle.dump(records, f, cPickle.HIGHEST_PROTOCOL)
            finally:
                f.close()
            os.chmod(cache_file, OUTPUT_FILE_MODE)
            print "Cached %d records to %s" % (len(records), cache_file)
        except (IOError, cPickle.PicklingError), e:
            print "Cache write failed: %s" % str(e)

    # ---------------------------------------------------------------
    # Summary output
    # ---------------------------------------------------------------

    def _write_summary(self, source_path, records):
        """Write a parse summary file alongside the input."""
        output_dir = os.getcwdu()
        summary_path = os.path.join(
            output_dir,
            os.path.basename(source_path) + ".summary.txt",
        )
        try:
            f = file(summary_path, "w")
            try:
                f.write("Source: %s\n" % source_path)
                f.write("Layout: %s\n" % self._layout.layout_name)
                f.write("Records parsed: %d\n" % len(records))
                f.write("Total errors: %d\n" % long(self._error_count.value))

                error_records = [r for r in records if r.has_errors()]
                f.write("Records with errors: %d\n" % len(error_records))
                for rec in error_records[:20]:
                    for err in rec.errors():
                        f.write("  Record #%d: %s\n" % (rec.record_number, err))
            finally:
                f.close()
            os.chmod(summary_path, OUTPUT_FILE_MODE)
        except IOError, e:
            print "Could not write summary: %s" % str(e)

    # ---------------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------------

    def records_parsed(self):
        return long(self._record_count.value)

    def errors_encountered(self):
        return long(self._error_count.value)
