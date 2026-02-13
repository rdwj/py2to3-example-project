# -*- coding: utf-8 -*-
"""
JSON data handler for the Legacy Industrial Data Platform.

Processes JSON feeds from the REST gateway that bridges the plant
network to the corporate IT systems.  These feeds contain sensor
metadata, work order records, and inventory updates.  The gateway
sends JSON as UTF-8 encoded byte streams over HTTP.

The handler also provides a fallback serialization path using pickle
for internal record caching when JSON round-trip fidelity is not
required (e.g. temporary inter-process data passing via shared NFS).
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import json
import time
import pickle
import io

from core.exceptions import DataError, ParseError
from core.config_loader import load_platform_config


# Maximum size of a JSON document we will attempt to parse in one shot.
# Larger documents are streamed via the record-at-a-time interface.
MAX_JSON_SIZE = 50 * 1024 * 1024   # 50 MB

# Default encoding for reading JSON byte streams.
JSON_DEFAULT_ENCODING = "utf-8"


# ---------------------------------------------------------------------------
# JsonRecordSet -- a batch of records with metadata
# ---------------------------------------------------------------------------

class JsonRecordSet(object):
    """A collection of JSON records with batch metadata.

    Represents a single REST gateway response payload, which contains
    an array of records plus envelope fields (timestamp, source, count).
    """

    def __init__(self, source_id=None):
        self.source_id = source_id
        self.records = []
        self.received_at = time.time()
        self.metadata = {}

    def add_record(self, record):
        self.records.append(record)

    def count(self):
        return len(self.records)

    def iter_records(self):
        return iter(self.records)

    def get_metadata(self, key, default=None):
        if key in self.metadata:
            return self.metadata[key]
        return default

    def set_metadata(self, key, value):
        self.metadata[key] = value

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "received_at": self.received_at,
            "count": len(self.records),
            "metadata": self.metadata,
            "records": self.records,
        }

    def __repr__(self):
        return "JsonRecordSet(source=%r, count=%d)" % (
            self.source_id, len(self.records),
        )


# ---------------------------------------------------------------------------
# JsonHandler -- main JSON processing engine
# ---------------------------------------------------------------------------

class JsonHandler(object):
    """Loads, validates, and transforms JSON data from REST gateway feeds."""

    def __init__(self, default_encoding=None):
        self._default_encoding = default_encoding or JSON_DEFAULT_ENCODING
        self._config = load_platform_config()
        self._validation_errors = []

    def load_file(self, file_path):
        """Load a JSON file into a JsonRecordSet.

        Reads the file as text and passes to ``json.loads()``.
        """
        stat = os.stat(file_path)
        if stat.st_size > MAX_JSON_SIZE:
            raise DataError(
                "JSON file too large: %d bytes (max %d)" % (stat.st_size, MAX_JSON_SIZE)
            )

        f = open(file_path, "rb")
        try:
            raw_bytes = f.read()
        finally:
            f.close()

        return self.load_bytes(raw_bytes, source_id=file_path)

    def load_bytes(self, raw_bytes, source_id=None):
        """Parse JSON from a byte string.

        In Python 3, ``json.loads()`` accepts both ``str`` and ``bytes``.
        The ``encoding`` parameter was removed in Python 3.9+.
        """
        try:
            if isinstance(raw_bytes, bytes):
                raw_bytes = raw_bytes.decode(self._default_encoding)
            data = json.loads(raw_bytes)
        except (ValueError, TypeError) as e:
            raise ParseError("JSON parse error from %s: %s" % (source_id, str(e)))

        return self._build_record_set(data, source_id)

    def load_stream(self, stream, source_id=None):
        """Parse JSON from a file-like stream using io.BytesIO for buffering.

        Reads the entire stream into a buffer first, then parses.
        """
        buf = io.BytesIO()
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            buf.write(chunk)

        raw_bytes = buf.getvalue()
        buf.close()
        return self.load_bytes(raw_bytes, source_id=source_id)

    def dump_to_file(self, record_set, file_path, pretty=False):
        """Serialize a JsonRecordSet to a JSON file.

        Uses ``json.dumps()`` with ``ensure_ascii=False`` to allow
        direct unicode output for non-ASCII sensor labels.
        """
        data = record_set.to_dict()

        kwargs = {
            "ensure_ascii": False,
        }
        if pretty:
            kwargs["indent"] = 2
            kwargs["sort_keys"] = True

        json_str = json.dumps(data, **kwargs)

        f = open(file_path, "w", encoding=self._default_encoding)
        try:
            f.write(json_str)
        finally:
            f.close()

    def dump_to_stream(self, record_set, pretty=False):
        """Serialize a JsonRecordSet to an io.BytesIO buffer and return it."""
        data = record_set.to_dict()

        kwargs = {
            "ensure_ascii": False,
        }
        if pretty:
            kwargs["indent"] = 2

        json_str = json.dumps(data, **kwargs)
        json_bytes = json_str.encode(self._default_encoding)

        buf = io.BytesIO()
        buf.write(json_bytes)
        buf.seek(0)
        return buf

    # ---------------------------------------------------------------
    # pickle fallback serialization
    # ---------------------------------------------------------------

    def pickle_record_set(self, record_set, file_path):
        """Serialize a JsonRecordSet using pickle for fast inter-process
        caching.  This is used for the temporary staging area on the
        shared NFS mount where the batch processor and the real-time
        engine exchange data.
        """
        f = open(file_path, "wb")
        try:
            pickle.dump(record_set, f, pickle.HIGHEST_PROTOCOL)
        finally:
            f.close()

    def unpickle_record_set(self, file_path):
        """Deserialize a pickle'd JsonRecordSet from the staging area."""
        f = open(file_path, "rb")
        try:
            data = pickle.load(f)
        finally:
            f.close()

        if not isinstance(data, JsonRecordSet):
            raise DataError(
                "Unpickled object is not a JsonRecordSet: %s" % type(data).__name__
            )
        return data

    # ---------------------------------------------------------------
    # Validation and transformation
    # ---------------------------------------------------------------

    def validate_records(self, record_set, required_fields):
        """Validate that all records in a set contain the required fields."""
        self._validation_errors = []
        valid_records = []

        for idx, record in enumerate(record_set.iter_records()):
            missing = []
            for field in required_fields:
                if field not in record:
                    missing.append(field)
            if missing:
                self._validation_errors.append(
                    "Record %d missing fields: %s" % (idx, ", ".join(missing))
                )
            else:
                valid_records.append(record)

        return valid_records

    def transform_records(self, record_set, field_map, value_transforms=None):
        """Apply field renaming and value transformations to all records.

        *field_map* is a dict of {old_name: new_name}.
        *value_transforms* is a dict of {field_name: callable}.
        """
        if value_transforms is None:
            value_transforms = {}

        result = JsonRecordSet(source_id=record_set.source_id)
        result.metadata = dict(record_set.metadata)

        for record in record_set.iter_records():
            new_record = {}
            for key, value in record.items():
                new_key = field_map.get(key, key)

                if new_key in value_transforms:
                    try:
                        value = value_transforms[new_key](value)
                    except Exception as e:
                        self._validation_errors.append(
                            "Transform error for %s: %s" % (new_key, str(e))
                        )
                new_record[new_key] = value
            result.add_record(new_record)

        return result

    def _build_record_set(self, data, source_id):
        """Build a JsonRecordSet from parsed JSON data.

        Handles two payload formats:
        1. An array of records (bare list)
        2. An envelope object with 'records' key and metadata
        """
        record_set = JsonRecordSet(source_id=source_id)

        if isinstance(data, list):
            for item in data:
                record_set.add_record(item)
        elif isinstance(data, dict):
            # Extract metadata from envelope
            for key in data.keys():
                if key == "records":
                    continue
                record_set.set_metadata(key, data[key])

            records = data.get("records", [])
            if isinstance(records, list):
                for item in records:
                    record_set.add_record(item)
            else:
                # Single record in envelope
                record_set.add_record(data)
        else:
            raise ParseError(
                "Unexpected JSON root type: %s" % type(data).__name__
            )

        return record_set

    def validation_errors(self):
        return list(self._validation_errors)
