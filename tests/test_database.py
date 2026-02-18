# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/database.py

Captures current behavior of database operations including:
- SQLite connection and schema management
- BLOB handling with bytes/str boundaries
- cPickle serialization in BLOBs (protocol 2)
- Transaction context manager
- Query builder fluent API
- copy_reg custom pickle reducers
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sqlite3
import tempfile
import time
from unittest import mock

import pytest

from src.storage.database import (
    DatabaseManager,
    QueryBuilder,
    TransactionContext,
    _pickle_data_point,
    _unpickle_data_point,
)
from src.core.types import DataPoint
from src.core.exceptions import DatabaseError, StorageError


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db):
    """Create a DatabaseManager with a temporary database."""
    mgr = DatabaseManager(temp_db)
    mgr.connect()
    mgr.ensure_schema()
    yield mgr
    mgr.close()


class TestQueryBuilder:
    """Test the fluent SQL query builder."""

    def test_simple_select(self):
        """Basic SELECT without filters."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.build()
        assert sql == "SELECT * FROM sensor_readings"
        assert params == ()

    def test_select_with_columns(self):
        """SELECT specific columns."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.select("id", "tag", "value").build()
        assert sql == "SELECT id, tag, value FROM sensor_readings"
        assert params == ()

    def test_where_clause(self):
        """WHERE with parameters."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.where("tag = ?", "TEMP_001").build()
        assert "WHERE tag = ?" in sql
        assert params == ("TEMP_001",)

    def test_multiple_where_clauses(self):
        """Multiple WHERE conditions joined with AND."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.where("tag = ?", "TEMP_001").where("quality >= ?", 192).build()
        assert "WHERE tag = ? AND quality >= ?" in sql
        assert params == ("TEMP_001", 192)

    def test_order_by(self):
        """ORDER BY clause."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.order_by("timestamp", "DESC").build()
        assert "ORDER BY timestamp DESC" in sql

    def test_limit(self):
        """LIMIT clause."""
        qb = QueryBuilder("sensor_readings")
        sql, params = qb.limit(50).build()
        assert "LIMIT 50" in sql

    def test_full_query_chain(self):
        """Test complete fluent chain."""
        qb = QueryBuilder("events")
        sql, params = (
            qb.select("id", "event_type", "timestamp")
            .where("event_type = ?", "alarm")
            .where("timestamp > ?", 1234567890.0)
            .order_by("timestamp", "DESC")
            .limit(100)
            .build()
        )
        assert "SELECT id, event_type, timestamp FROM events" in sql
        assert "WHERE event_type = ? AND timestamp > ?" in sql
        assert "ORDER BY timestamp DESC" in sql
        assert "LIMIT 100" in sql
        assert params == ("alarm", 1234567890.0)


class TestTransactionContext:
    """Test transaction context manager behavior."""

    def test_commit_on_success(self, temp_db):
        """Transaction commits when no exception occurs."""
        conn = sqlite3.connect(temp_db)
        conn.execute("CREATE TABLE test (id INTEGER, value TEXT)")

        with TransactionContext(conn) as txn:
            txn.execute("INSERT INTO test (id, value) VALUES (1, 'test')")

        cursor = conn.execute("SELECT value FROM test WHERE id=1")
        row = cursor.fetchone()
        assert row[0] == "test"
        conn.close()

    def test_rollback_on_exception(self, temp_db):
        """Transaction rolls back when exception occurs."""
        conn = sqlite3.connect(temp_db)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

        try:
            with TransactionContext(conn) as txn:
                txn.execute("INSERT INTO test (id, value) VALUES (1, 'test')")
                raise ValueError("Intentional error")
        except ValueError:
            pass

        cursor = conn.execute("SELECT COUNT(*) FROM test")
        count = cursor.fetchone()[0]
        assert count == 0
        conn.close()


class TestDatabaseManager:
    """Test database manager operations."""

    def test_connect_and_schema_creation(self, temp_db):
        """Test connection and schema initialization."""
        mgr = DatabaseManager(temp_db)
        mgr.connect()
        mgr.ensure_schema()

        # Verify tables exist
        cursor = mgr._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "sensor_readings" in tables
        assert "events" in tables
        assert "object_store" in tables

        mgr.close()

    def test_store_reading_basic(self, db_manager):
        """Test storing a basic sensor reading."""
        dp = DataPoint("TEMP_001", 25.5, quality=192)
        db_manager.store_reading("sensor_1", dp)

        rows = db_manager.fetch_readings("TEMP_001", limit=10)
        assert len(rows) == 1
        assert rows[0][1] == "TEMP_001"  # tag
        assert abs(rows[0][2] - 25.5) < 0.01  # value

    def test_store_reading_with_raw_frame(self, db_manager):
        """Test storing reading with binary BLOB frame."""
        dp = DataPoint("PRES_002", 101.3, quality=192)
        raw_frame = b"\xAA\x06\x00\x02\x01\x65\x0A\xB7"

        db_manager.store_reading("sensor_2", dp, raw_frame=raw_frame)

        # Retrieve the raw_frame BLOB
        cursor = db_manager._conn.execute(
            "SELECT id, raw_frame FROM sensor_readings WHERE tag=? ORDER BY id DESC LIMIT 1",
            ("PRES_002",)
        )
        row = cursor.fetchone()
        assert row is not None
        # In Python 3, BLOB comes back as bytes
        blob_data = bytes(row[1]) if row[1] is not None else None
        assert blob_data == raw_frame

    def test_store_readings_batch(self, db_manager):
        """Test bulk insert with transaction."""
        readings = [
            ("sensor_1", DataPoint("TEMP_001", 20.0, quality=192), None),
            ("sensor_2", DataPoint("TEMP_002", 21.0, quality=192), None),
            ("sensor_3", DataPoint("TEMP_003", 22.0, quality=192), None),
        ]

        db_manager.store_readings_batch(readings)

        for sensor_id, dp, _ in readings:
            rows = db_manager.fetch_readings(dp.tag, limit=1)
            assert len(rows) == 1

    def test_fetch_readings_with_limit(self, db_manager):
        """Test reading fetch with limit."""
        # Insert multiple readings
        for i in range(15):
            dp = DataPoint("FLOW_001", float(i), quality=192, timestamp=time.time() + i)
            db_manager.store_reading("sensor_1", dp)

        rows = db_manager.fetch_readings("FLOW_001", limit=5)
        assert len(rows) == 5

    def test_get_raw_frame(self, db_manager):
        """Test retrieving BLOB by reading ID."""
        dp = DataPoint("VIB_001", 0.05, quality=192)
        raw_frame = b"\xFF\xFE\xFD\xFC"

        db_manager.store_reading("sensor_1", dp, raw_frame=raw_frame)

        # Get the reading ID
        cursor = db_manager._conn.execute(
            "SELECT id FROM sensor_readings WHERE tag=? ORDER BY id DESC LIMIT 1",
            ("VIB_001",)
        )
        reading_id = cursor.fetchone()[0]

        retrieved = db_manager.get_raw_frame(reading_id)
        assert retrieved == raw_frame

    def test_log_event_simple(self, db_manager):
        """Test event logging without payload."""
        db_manager.log_event("system_startup", "main")

        events = db_manager.fetch_events(event_type="system_startup")
        assert len(events) == 1
        assert events[0]["event_type"] == "system_startup"
        assert events[0]["source"] == "main"

    def test_log_event_with_pickle_payload(self, db_manager):
        """Test event logging with pickled object payload."""
        payload = {"alarm_id": 123, "severity": 4, "tags": ["TEMP_001", "TEMP_002"]}

        db_manager.log_event("alarm_triggered", "alarm_engine", payload_obj=payload)

        events = db_manager.fetch_events(event_type="alarm_triggered")
        assert len(events) == 1
        assert events[0]["payload"] == payload

    def test_fetch_events_with_limit(self, db_manager):
        """Test event fetching with limit."""
        for i in range(10):
            db_manager.log_event("test_event_%d" % i, "test")

        events = db_manager.fetch_events(limit=5)
        assert len(events) == 5

    def test_put_and_get_object(self, db_manager):
        """Test object store with cPickle serialization."""
        test_obj = {
            "config_version": 2,
            "sensors": ["TEMP_001", "PRES_002"],
            "thresholds": {"high": 100.0, "low": 0.0},
        }

        db_manager.put_object("sensor_config_v2", test_obj)
        retrieved = db_manager.get_object("sensor_config_v2")

        assert retrieved == test_obj

    def test_get_object_nonexistent(self, db_manager):
        """Test retrieving non-existent object returns None."""
        result = db_manager.get_object("does_not_exist")
        assert result is None

    def test_purge_readings_before(self, db_manager):
        """Test purging old readings by timestamp."""
        now = time.time()
        old_time = now - 1000

        # Insert old reading
        dp_old = DataPoint("TEMP_001", 10.0, quality=192, timestamp=old_time)
        db_manager.store_reading("sensor_1", dp_old)

        # Insert new reading
        dp_new = DataPoint("TEMP_002", 20.0, quality=192, timestamp=now)
        db_manager.store_reading("sensor_2", dp_new)

        # Purge readings older than (now - 500)
        deleted = db_manager.purge_readings_before(now - 500)
        assert deleted == 1

        # Verify old reading is gone, new reading remains
        rows = db_manager.fetch_readings("TEMP_001")
        assert len(rows) == 0

        rows = db_manager.fetch_readings("TEMP_002")
        assert len(rows) == 1

    def test_vacuum(self, db_manager):
        """Test VACUUM operation (non-fatal if fails)."""
        # Just ensure it doesn't crash
        db_manager.vacuum()

    def test_connection_failure(self):
        """Test database connection error handling."""
        with pytest.raises(DatabaseError):
            mgr = DatabaseManager("/invalid/path/database.db")
            mgr.connect()


class TestDataPointPickling:
    """Test custom pickle support for DataPoint via copy_reg."""

    def test_pickle_unpickle_round_trip(self):
        """Test DataPoint pickle/unpickle round-trip."""
        dp = DataPoint("SENSOR_123", 42.5, quality=192, timestamp=1234567890.0)

        unpickled_dp = _unpickle_data_point(
            dp.tag, dp.value, dp.timestamp, dp.quality
        )

        assert unpickled_dp.tag == dp.tag
        assert unpickled_dp.value == dp.value
        assert unpickled_dp.timestamp == dp.timestamp
        assert unpickled_dp.quality == dp.quality

    def test_pickle_reducer(self):
        """Test the custom pickle reducer function."""
        dp = DataPoint("TEST_TAG", 99.9, quality=192, timestamp=9999.0)

        # The reducer should return (constructor, args_tuple)
        constructor, args = _pickle_data_point(dp)
        assert constructor == _unpickle_data_point
        assert args == (dp.tag, dp.value, dp.timestamp, dp.quality)


class TestEncodingBoundaries:
    """Test bytes/str handling at database boundaries."""

    def test_text_columns_with_unicode(self, db_manager):
        """Test storing unicode text in TEXT columns."""
        # In Py2, TEXT columns return str (bytes); test round-trip
        dp = DataPoint(u"SENSOR_日本語", 100.0, quality=192)
        db_manager.store_reading("sensor_unicode", dp)

        rows = db_manager.fetch_readings(u"SENSOR_日本語")
        assert len(rows) == 1
        # Tag comes back as str in Py2; should match when encoded
        tag_from_db = rows[0][1]
        if isinstance(tag_from_db, bytes):
            assert tag_from_db == u"SENSOR_日本語".encode("utf-8")

    def test_blob_binary_data(self, db_manager):
        """Test BLOB with various binary patterns."""
        # Test with non-ASCII bytes
        binary_data = b"\x00\x01\x02\x03\xFF\xFE\xFD\xFC"
        dp = DataPoint("BINARY_TEST", 0.0, quality=192)

        db_manager.store_reading("sensor_bin", dp, raw_frame=binary_data)

        cursor = db_manager._conn.execute(
            "SELECT raw_frame FROM sensor_readings WHERE tag=? ORDER BY id DESC LIMIT 1",
            ("BINARY_TEST",)
        )
        row = cursor.fetchone()
        blob = bytes(row[0]) if row[0] is not None else None
        assert blob == binary_data
