# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/database.py

Captures pre-migration behavior of:
- QueryBuilder fluent SQL construction
- TransactionContext commit/rollback
- DatabaseManager CRUD with pickle serialization via cPickle
- BLOB storage and retrieval (buffer -> str conversion)
- copy_reg pickle reducer for DataPoint
"""


import os
import sys
import time
import sqlite3
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.storage.database import QueryBuilder, DatabaseManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path that is cleaned up after test."""
    db_path = str(tmp_path / "test.db")
    yield db_path


@pytest.fixture
def db_manager(tmp_db):
    """Provide a connected DatabaseManager with schema initialized."""
    mgr = DatabaseManager(tmp_db)
    mgr.connect()
    mgr.ensure_schema()
    yield mgr
    mgr.close()


@pytest.fixture
def sample_data_point():
    """Create a DataPoint for use in database tests."""
    from src.core.types import DataPoint
    return DataPoint("TEMP-001", 23.5, timestamp=1000000.0, quality=192)


# ---------------------------------------------------------------------------
# QueryBuilder
# ---------------------------------------------------------------------------

class TestQueryBuilder:
    """Characterize the fluent SQL builder."""

    def test_basic_select_all(self):
        """Captures: SELECT * FROM <table> with no constraints."""
        sql, params = QueryBuilder("sensor_readings").build()
        assert sql == "SELECT * FROM sensor_readings"
        assert params == ()

    def test_select_specific_columns(self):
        """Captures: column list in SELECT clause."""
        sql, params = (QueryBuilder("events")
                       .select("id", "event_type", "timestamp")
                       .build())
        assert "id, event_type, timestamp" in sql
        assert params == ()

    def test_where_single_clause(self):
        """Captures: single WHERE clause with parameter binding."""
        sql, params = (QueryBuilder("sensor_readings")
                       .where("tag = ?", "TEMP-001")
                       .build())
        assert "WHERE tag = ?" in sql
        assert params == ("TEMP-001",)

    def test_where_multiple_clauses(self):
        """Captures: multiple WHERE clauses joined with AND."""
        sql, params = (QueryBuilder("sensor_readings")
                       .where("tag = ?", "TEMP-001")
                       .where("quality > ?", 100)
                       .build())
        assert "WHERE tag = ? AND quality > ?" in sql
        assert params == ("TEMP-001", 100)

    def test_order_by(self):
        """Captures: ORDER BY clause with direction."""
        sql, _ = (QueryBuilder("events")
                  .order_by("timestamp", "DESC")
                  .build())
        assert "ORDER BY timestamp DESC" in sql

    def test_limit(self):
        """Captures: LIMIT clause with integer formatting."""
        sql, _ = QueryBuilder("events").limit(50).build()
        assert "LIMIT 50" in sql

    def test_full_query_chain(self):
        """Captures: complete fluent chain producing full SQL."""
        sql, params = (QueryBuilder("sensor_readings")
                       .select("tag", "value")
                       .where("quality >= ?", 192)
                       .order_by("timestamp", "DESC")
                       .limit(10)
                       .build())
        assert sql.startswith("SELECT tag, value FROM sensor_readings")
        assert "WHERE quality >= ?" in sql
        assert "ORDER BY timestamp DESC" in sql
        assert "LIMIT 10" in sql
        assert params == (192,)


# ---------------------------------------------------------------------------
# DatabaseManager -- reading / writing
# ---------------------------------------------------------------------------

class TestDatabaseManagerReadings:
    """Characterize sensor reading CRUD operations."""

    def test_store_and_fetch_reading(self, db_manager, sample_data_point):
        """Captures: basic store + fetch round-trip for a sensor reading."""
        db_manager.store_reading("S001", sample_data_point)
        rows = db_manager.fetch_readings("TEMP-001", limit=10)
        assert len(rows) >= 1
        row = rows[0]
        assert row[0] == "S001"       # sensor_id
        assert row[1] == "TEMP-001"   # tag
        assert abs(row[2] - 23.5) < 0.01  # value

    def test_store_reading_with_raw_frame(self, db_manager, sample_data_point):
        """Captures: BLOB storage of raw protocol frame bytes."""
        raw = b"\xAA\x08\x00\x01\x01\x00\xE7\x42"
        db_manager.store_reading("S001", sample_data_point, raw_frame=raw)
        rows = db_manager.fetch_readings("TEMP-001", limit=1)
        assert len(rows) == 1
        # raw_frame column should be present (may be buffer type in Py2)
        assert rows[0][5] is not None

    @pytest.mark.py2_behavior
    def test_get_raw_frame_returns_bytes(self, db_manager, sample_data_point):
        """Captures: get_raw_frame returns bytes in Py3 (was str in Py2).
        In Py3, BLOB data is retrieved as bytes via bytes(row[0])."""
        raw = b"\x01\x02\x03\x04"
        db_manager.store_reading("S002", sample_data_point, raw_frame=raw)
        # Need to get the reading_id
        rows = db_manager.fetch_readings("TEMP-001", limit=1)
        # fetch by id=1 (first inserted)
        result = db_manager.get_raw_frame(1)
        assert result is not None
        assert isinstance(result, bytes)

    def test_fetch_readings_respects_limit(self, db_manager):
        """Captures: LIMIT clause applied to reading queries."""
        from src.core.types import DataPoint
        for i in range(5):
            dp = DataPoint("FLOW-001", float(i), timestamp=1000000.0 + i, quality=192)
            db_manager.store_reading("S003", dp)
        rows = db_manager.fetch_readings("FLOW-001", limit=3)
        assert len(rows) == 3

    def test_store_readings_batch(self, db_manager):
        """Captures: bulk insert via transaction context manager."""
        from src.core.types import DataPoint
        readings = []
        for i in range(3):
            dp = DataPoint("BATCH-%03d" % i, float(i), timestamp=1000000.0 + i)
            readings.append(("S004", dp, None))
        db_manager.store_readings_batch(readings)
        for i in range(3):
            rows = db_manager.fetch_readings("BATCH-%03d" % i)
            assert len(rows) >= 1

    def test_purge_readings_before(self, db_manager):
        """Captures: DELETE with timestamp cutoff."""
        from src.core.types import DataPoint
        dp_old = DataPoint("PURGE-TEST", 1.0, timestamp=100.0)
        dp_new = DataPoint("PURGE-TEST", 2.0, timestamp=9999999.0)
        db_manager.store_reading("S005", dp_old)
        db_manager.store_reading("S005", dp_new)
        deleted = db_manager.purge_readings_before(500.0)
        assert deleted >= 1
        remaining = db_manager.fetch_readings("PURGE-TEST")
        assert len(remaining) >= 1


# ---------------------------------------------------------------------------
# DatabaseManager -- events with pickle serialization
# ---------------------------------------------------------------------------

class TestDatabaseManagerEvents:
    """Characterize event logging with cPickle serialization."""

    def test_log_event_no_payload(self, db_manager):
        """Captures: event insert without serialized payload."""
        db_manager.log_event("ALARM", "sensor_001")
        events = db_manager.fetch_events("ALARM")
        assert len(events) >= 1
        assert events[0]["event_type"] == "ALARM"
        assert events[0]["payload"] is None

    @pytest.mark.py2_behavior
    def test_log_event_with_dict_payload(self, db_manager):
        """Captures: event insert with cPickle-serialized dict payload.
        Protocol 2 pickle format; Py3 cPickle -> pickle."""
        payload = {"severity": 3, "message": "High temperature"}
        db_manager.log_event("ALARM", "sensor_002", payload_obj=payload)
        events = db_manager.fetch_events("ALARM")
        assert len(events) >= 1
        recovered = events[0]["payload"]
        assert recovered == payload

    @pytest.mark.py2_behavior
    def test_event_pickle_roundtrip_with_unicode(self, db_manager):
        """Captures: pickle roundtrip of unicode strings through BLOB column.
        cPickle protocol 2 handles unicode differently than Py3 pickle."""
        payload = {"tag": "caf\u00e9", "desc": "r\u00e9sum\u00e9"}
        db_manager.log_event("INFO", "test", payload_obj=payload)
        events = db_manager.fetch_events("INFO")
        assert events[0]["payload"] == payload

    def test_fetch_events_with_type_filter(self, db_manager):
        """Captures: fetch_events filters by event_type."""
        db_manager.log_event("ALARM", "s1")
        db_manager.log_event("INFO", "s2")
        alarms = db_manager.fetch_events("ALARM")
        assert all(e["event_type"] == "ALARM" for e in alarms)

    def test_fetch_events_no_filter(self, db_manager):
        """Captures: fetch_events without filter returns all types."""
        db_manager.log_event("ALARM", "s1")
        db_manager.log_event("INFO", "s2")
        all_events = db_manager.fetch_events()
        assert len(all_events) >= 2


# ---------------------------------------------------------------------------
# DatabaseManager -- object store (pickle round-trip)
# ---------------------------------------------------------------------------

class TestDatabaseManagerObjectStore:
    """Characterize the pickle-based object store."""

    @pytest.mark.py2_behavior
    def test_put_and_get_simple_dict(self, db_manager):
        """Captures: cPickle protocol 2 round-trip of a simple dict."""
        obj = {"sensor": "TEMP-001", "calibration": [1.0, 0.5, -0.02]}
        db_manager.put_object("cal_temp001", obj)
        result = db_manager.get_object("cal_temp001")
        assert result == obj

    @pytest.mark.py2_behavior
    def test_put_and_get_unicode_values(self, db_manager):
        """Captures: cPickle handles unicode strings in protocol 2."""
        obj = {"label": "Temp\u00e9rature", "unit": "\u00b0C"}
        db_manager.put_object("unicode_test", obj)
        result = db_manager.get_object("unicode_test")
        assert result == obj

    @pytest.mark.py2_behavior
    def test_put_and_get_nested_structure(self, db_manager):
        """Captures: cPickle protocol 2 with nested dicts and lists."""
        obj = {
            "sensors": [
                {"id": "S001", "type": 0x01, "readings": [23.5, 24.1]},
                {"id": "S002", "type": 0x02, "readings": [101325, 101400]},
            ],
            "timestamp": 1000000.0,
        }
        db_manager.put_object("nested", obj)
        result = db_manager.get_object("nested")
        assert result == obj

    def test_get_nonexistent_key_returns_none(self, db_manager):
        """Captures: missing key returns None, not an error."""
        assert db_manager.get_object("does_not_exist") is None

    @pytest.mark.py2_behavior
    def test_put_overwrites_existing(self, db_manager):
        """Captures: INSERT OR REPLACE semantics on key collision."""
        db_manager.put_object("key1", {"version": 1})
        db_manager.put_object("key1", {"version": 2})
        result = db_manager.get_object("key1")
        assert result == {"version": 2}


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestDatabaseEncodingBoundaries:
    """Test encoding edge cases at the database boundary."""

    @pytest.mark.py2_behavior
    def test_store_reading_with_unicode_tag(self, db_manager):
        """Captures: unicode tag stored in TEXT column.
        Py2 sqlite3 returns str for TEXT; Py3 returns str (text)."""
        from src.core.types import DataPoint
        dp = DataPoint("caf\u00e9-sensor", 42.0, timestamp=1000000.0)
        db_manager.store_reading("S-\u00e9", dp)
        rows = db_manager.fetch_readings("caf\u00e9-sensor")
        assert len(rows) >= 1

    @pytest.mark.py2_behavior
    def test_store_binary_blob_with_high_bytes(self, db_manager, sample_data_point):
        """Captures: BLOB column stores arbitrary binary including 0xFF bytes."""
        raw = b"\x00\x7F\x80\xFF\xAA\x55"
        db_manager.store_reading("S-BIN", sample_data_point, raw_frame=raw)
        rows = db_manager.fetch_readings("TEMP-001", limit=1)
        assert rows[0][5] is not None

    @pytest.mark.py2_behavior
    def test_pickle_latin1_payload(self, db_manager):
        """Captures: cPickle roundtrip of Latin-1 encoded byte strings."""
        payload = {"raw": b"\xe9\xe8\xea", "label": "caf\u00e9"}
        db_manager.log_event("TEST", "enc", payload_obj=payload)
        events = db_manager.fetch_events("TEST")
        assert events[0]["payload"]["raw"] == b"\xe9\xe8\xea"
