# -*- coding: utf-8 -*-
"""
CSV processor for the Legacy Industrial Data Platform.

Handles CSV files exported from various plant historians and third-party
systems.  These files arrive in a zoo of encodings -- Latin-1 from the
German site, Shift-JIS from the Japanese facility, UTF-8 from the newer
REST API exports, and plain ASCII from the legacy DCS historian.  The
processor maps historian-specific column names to the platform's internal
field names via a configurable CsvFieldMapper.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import csv
import codecs
import io

from src.core.exceptions import DataError, EncodingError, ParseError
from src.core.string_helpers import safe_decode, safe_encode, detect_encoding
from src.core.config_loader import load_platform_config


# In Python 3 the csv module works with text mode, not binary.
CSV_READ_MODE = "r"

# Default encoding assumption when no BOM or hint is present.
DEFAULT_ENCODING = "ascii"

# BOM markers for auto-detection (as bytes for comparison against raw reads)
_BOM_UTF8 = b"\xef\xbb\xbf"
_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF16_BE = b"\xfe\xff"


# ---------------------------------------------------------------------------
# CSV reader/writer -- simplified for Python 3 (native unicode support)
# ---------------------------------------------------------------------------

def unicode_csv_reader(file_obj, dialect=csv.excel, **kwargs):
    """Wrap ``csv.reader`` to yield rows of strings.

    In Python 3 the csv module operates on text strings natively, so
    no decode step is needed.  The ``encoding`` kwarg from the Py2
    wrapper is accepted and ignored for call-site compatibility.
    """
    kwargs.pop("encoding", None)
    reader = csv.reader(file_obj, dialect=dialect, **kwargs)
    for row in reader:
        yield row


def unicode_csv_writer(file_obj, dialect=csv.excel, **kwargs):
    """Return a csv.writer wrapper.

    In Python 3 the csv module handles str natively.  The ``encoding``
    kwarg is accepted and ignored for call-site compatibility.
    """
    kwargs.pop("encoding", None)
    writer = csv.writer(file_obj, dialect=dialect, **kwargs)

    class _UnicodeWriter(object):
        def writerow(self, row):
            writer.writerow([str(cell) for cell in row])

        def writerows(self, rows):
            for row in rows:
                self.writerow(row)

    return _UnicodeWriter()


# ---------------------------------------------------------------------------
# CsvFieldMapper -- translates historian column names to internal names
# ---------------------------------------------------------------------------

class CsvFieldMapper(object):
    """Maps external CSV column headers to the platform's internal field names.

    Different historians export with different column names for the same
    concept.  For example, the timestamp column might be called 'Time',
    'TIMESTAMP', 'Date/Time', or 'Zeitstempel' depending on the source.
    """

    def __init__(self):
        self._mappings = {}
        self._transforms = {}

    def add_mapping(self, external_name, internal_name, transform_func=None):
        """Register a column name mapping.

        The *external_name* is stored normalised to lowercase for
        case-insensitive matching.
        """
        key = external_name.lower().strip()
        self._mappings[key] = internal_name
        if transform_func is not None:
            self._transforms[internal_name] = transform_func

    def map_header(self, header_row):
        """Map an entire header row, returning a list of internal field names.

        Unrecognised columns are passed through unchanged.
        """
        result = []
        for col in header_row:
            key = col.lower().strip()
            if key in self._mappings:
                result.append(self._mappings[key])
            else:
                result.append(col)
        return result

    def transform_value(self, internal_name, raw_value):
        """Apply the registered transform function for a field, if any."""
        if internal_name in self._transforms:
            return self._transforms[internal_name](raw_value)
        return raw_value


# ---------------------------------------------------------------------------
# CsvProcessor -- main CSV ingestion engine
# ---------------------------------------------------------------------------

class CsvProcessor(object):
    """Process CSV files from plant historians into internal record dicts.

    Handles encoding detection, BOM stripping, field mapping, and value
    transformation in a single pipeline.
    """

    def __init__(self, field_mapper=None, default_encoding=None):
        self._field_mapper = field_mapper
        self._default_encoding = default_encoding or DEFAULT_ENCODING
        self._config = load_platform_config()
        self._processed_count = 0
        self._error_count = 0

    def read_csv(self, file_path, encoding=None, has_header=True):
        """Read a CSV file and return a list of record dicts.

        Opens the file in text mode with the detected encoding, as
        required by the Python 3 csv module.
        """
        if encoding is None:
            encoding = self._detect_file_encoding(file_path)

        records = []
        f = open(file_path, "r", newline="", encoding=encoding)
        try:
            reader = unicode_csv_reader(f)
            header = None

            for row_num, row in enumerate(reader):
                if has_header and row_num == 0:
                    header = row
                    if self._field_mapper is not None:
                        header = self._field_mapper.map_header(header)
                    continue

                try:
                    record = self._build_record(header, row, row_num)
                    records.append(record)
                    self._processed_count += 1
                except DataError as e:
                    self._error_count += 1
        finally:
            f.close()

        return records

    def read_csv_string(self, csv_text, encoding="utf-8", has_header=True):
        """Parse CSV data from an in-memory string.

        Uses io.StringIO to wrap the text for the csv reader.
        """
        if isinstance(csv_text, bytes):
            csv_text = csv_text.decode(encoding)

        buf = io.StringIO(csv_text)
        reader = unicode_csv_reader(buf)
        records = []
        header = None

        for row_num, row in enumerate(reader):
            if has_header and row_num == 0:
                header = row
                if self._field_mapper is not None:
                    header = self._field_mapper.map_header(header)
                continue
            try:
                record = self._build_record(header, row, row_num)
                records.append(record)
            except DataError as e:
                self._error_count += 1

        return records

    def write_csv(self, file_path, records, field_names, encoding="utf-8"):
        """Write records to a CSV file.

        Opens in text mode with the requested encoding.
        """
        out = open(file_path, "w", newline="", encoding=encoding, errors="replace")
        try:
            writer = csv.writer(out)
            writer.writerow(field_names)

            for record in records:
                cells = []
                for name in field_names:
                    value = record.get(name, "")
                    cells.append(str(value))
                writer.writerow(cells)
        finally:
            out.close()

    def transcode_csv(self, input_path, output_path, from_encoding, to_encoding):
        """Read a CSV in one encoding and write it in another.

        Common use case: converting Latin-1 exports from the German site
        to UTF-8 for the central data warehouse.
        """
        records = self.read_csv(input_path, encoding=from_encoding)
        if not records:
            return 0

        field_names = list(records[0].keys())
        self.write_csv(output_path, records, field_names, encoding=to_encoding)
        return len(records)

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    def _build_record(self, header, row, row_num):
        """Build a record dict from a header and a data row."""
        if header is None:
            # No header -- use positional indices as keys
            record = {}
            for i, value in enumerate(row):
                record["field_%d" % i] = value
            return record

        if len(row) < len(header):
            # Pad short rows with empty strings
            row = row + [""] * (len(header) - len(row))

        record = {}
        for i, field_name in enumerate(header):
            if i < len(row):
                value = row[i]
                if self._field_mapper is not None:
                    value = self._field_mapper.transform_value(field_name, value)
                record[field_name] = value

        return record

    def _detect_file_encoding(self, file_path):
        """Detect file encoding from BOM, falling back to heuristic detection."""
        f = open(file_path, "rb")
        try:
            header = f.read(4)
        finally:
            f.close()

        if header[:3] == _BOM_UTF8:
            return "utf-8-sig"
        if header[:2] == _BOM_UTF16_LE:
            return "utf-16-le"
        if header[:2] == _BOM_UTF16_BE:
            return "utf-16-be"

        # No BOM -- read a larger sample and use heuristic detection
        f = open(file_path, "rb")
        try:
            sample = f.read(8192)
        finally:
            f.close()

        detected = detect_encoding(sample)
        if detected == "ascii":
            return self._default_encoding
        return detected

    def stats(self):
        """Return processing statistics."""
        return {
            "processed": self._processed_count,
            "errors": self._error_count,
        }
