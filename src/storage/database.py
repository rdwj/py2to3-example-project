# -*- coding: utf-8 -*-
"""
Database layer for the Legacy Industrial Data Platform.

SQLite-backed storage for sensor readings, event logs, and serialised
objects.  Custom pickle reducers registered via ``copy_reg`` (renamed
``copyreg`` in Py3) allow ``DataPoint`` to be stored in BLOB columns.
"""

import time
import sqlite3
import copy_reg
import cPickle
import types

from src.core.exceptions import DatabaseError, StorageError
from src.core.types import DataPoint

# -- Custom pickle support for DataPoint (old-style class) --

def _pickle_data_point(dp):
    """copy_reg reducer.  ``copy_reg`` renamed ``copyreg`` in Py3."""
    return _unpickle_data_point, (dp.tag, dp.value, dp.timestamp, dp.quality)

def _unpickle_data_point(tag, value, timestamp, quality):
    return DataPoint(tag, value, timestamp, quality)

copy_reg.pickle(types.InstanceType, _pickle_data_point)

# -- SQL templates --

_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS sensor_readings (id INTEGER PRIMARY KEY "
    "AUTOINCREMENT, sensor_id TEXT NOT NULL, tag TEXT NOT NULL, value REAL, "
    "quality INTEGER DEFAULT 192, timestamp REAL NOT NULL, raw_frame BLOB, "
    "created_at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "event_type TEXT NOT NULL, source TEXT, payload BLOB, timestamp REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS object_store (key TEXT PRIMARY KEY, "
    "pickled BLOB NOT NULL, protocol INTEGER DEFAULT 2, updated_at REAL NOT NULL)",
]


class QueryBuilder(object):
    """Fluent parameterised SQL builder.  sqlite3 returns ``str``
    (bytes) for TEXT in Py2, ``str`` (text) in Py3."""

    def __init__(self, table):
        self._table = table
        self._columns = ["*"]
        self._wheres, self._params = [], []
        self._order, self._limit = None, None

    def select(self, *cols):
        self._columns = list(cols)
        return self

    def where(self, clause, *params):
        self._wheres.append(clause)
        self._params.extend(params)
        return self

    def order_by(self, col, direction="ASC"):
        self._order = "%s %s" % (col, direction)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def build(self):
        sql = "SELECT %s FROM %s" % (", ".join(self._columns), self._table)
        if self._wheres:
            sql += " WHERE " + " AND ".join(self._wheres)
        if self._order:
            sql += " ORDER BY " + self._order
        if self._limit is not None:
            sql += " LIMIT %d" % self._limit
        return sql, tuple(self._params)


class TransactionContext(object):
    """Commit-on-success, rollback-on-failure context manager."""

    def __init__(self, connection):
        self._conn = connection

    def __enter__(self):
        self._conn.execute("BEGIN")
        print "  [txn] BEGIN"
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            try:
                self._conn.execute("COMMIT")
                print "  [txn] COMMIT"
            except StandardError, e:
                self._conn.execute("ROLLBACK")
                raise DatabaseError("commit failed: %s" % e)
        else:
            try:
                self._conn.execute("ROLLBACK")
                print "  [txn] ROLLBACK (%s)" % exc_type.__name__
            except StandardError, e:
                print "  [txn] ROLLBACK failed: %s" % e
            return False


class DatabaseManager(object):
    """SQLite storage engine.  Query TEXT comes back as ``str`` (bytes)
    in Py2.  BLOBs return ``buffer`` in Py2, ``bytes`` in Py3."""

    _INS_READING = (
        "INSERT INTO sensor_readings "
        "(sensor_id,tag,value,quality,timestamp,raw_frame,created_at) "
        "VALUES (?,?,?,?,?,?,?)")

    def __init__(self, db_path, timeout=10):
        self._db_path = db_path
        self._conn = None
        self._timeout = timeout

    def connect(self):
        try:
            self._conn = sqlite3.connect(self._db_path, timeout=self._timeout)
            self._conn.execute("PRAGMA journal_mode=WAL")
            print "Connected to database: %s" % self._db_path
        except Exception, e:
            raise DatabaseError("cannot open %s: %s" % (self._db_path, e))

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def ensure_schema(self):
        try:
            for s in _SCHEMA:
                self._conn.execute(s)
            self._conn.commit()
            print "Schema verified"
        except StandardError, e:
            raise DatabaseError("schema creation failed: %s" % e)

    def transaction(self):
        if self._conn is None:
            raise DatabaseError("not connected")
        return TransactionContext(self._conn)

    def store_reading(self, sensor_id, dp, raw_frame=None):
        """Insert a reading with optional raw protocol frame BLOB."""
        blob = sqlite3.Binary(raw_frame) if raw_frame is not None else None
        try:
            self._conn.execute(self._INS_READING, (
                sensor_id, dp.tag, dp.value, dp.quality,
                dp.timestamp, blob, time.time()))
            self._conn.commit()
            print "Stored reading: %s = %s" % (dp.tag, dp.value)
        except Exception, e:
            raise DatabaseError("insert failed for %s: %s" % (sensor_id, e))

    def store_readings_batch(self, readings):
        """Bulk insert ``(sensor_id, DataPoint, raw_frame)`` tuples."""
        with self.transaction() as conn:
            now = time.time()
            for sid, dp, raw in readings:
                blob = sqlite3.Binary(raw) if raw else None
                conn.execute(self._INS_READING, (
                    sid, dp.tag, dp.value, dp.quality, dp.timestamp, blob, now))
            print "Batch inserted %d readings" % len(readings)

    def fetch_readings(self, tag, limit=100):
        """Most recent readings.  TEXT columns are ``str`` (bytes) in Py2."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT sensor_id,tag,value,quality,timestamp,raw_frame "
                "FROM sensor_readings WHERE tag=? ORDER BY timestamp DESC LIMIT ?",
                (tag, limit))
            rows = cur.fetchall()
            print "Fetched %d readings for %s" % (len(rows), tag)
            return rows
        except Exception, e:
            raise DatabaseError("query failed for %s: %s" % (tag, e))

    def get_raw_frame(self, reading_id):
        """Retrieve BLOB.  Returns ``buffer`` in Py2, ``bytes`` in Py3."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT raw_frame FROM sensor_readings WHERE id=?", (reading_id,))
            row = cur.fetchone()
            return str(row[0]) if row and row[0] is not None else None
        except Exception, e:
            raise DatabaseError("BLOB retrieval failed for id %d: %s" % (reading_id, e))

    def log_event(self, event_type, source, payload_obj=None):
        """Record event.  Payload pickled with protocol 2 (highest in Py2;
        Py3 added protocols 3-5)."""
        blob = None
        if payload_obj is not None:
            try:
                blob = sqlite3.Binary(cPickle.dumps(payload_obj, 2))
            except StandardError, e:
                print "WARNING: pickle failed: %s" % e
        try:
            self._conn.execute(
                "INSERT INTO events (event_type,source,payload,timestamp) VALUES (?,?,?,?)",
                (event_type, source, blob, time.time()))
            self._conn.commit()
        except Exception, e:
            raise DatabaseError("event insert failed: %s" % e)

    def fetch_events(self, event_type=None, limit=50):
        qb = QueryBuilder("events").select("id","event_type","source","payload","timestamp")
        if event_type is not None:
            qb.where("event_type = ?", event_type)
        sql, params = qb.order_by("timestamp","DESC").limit(limit).build()
        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            results = []
            for row in cur.fetchall():
                payload = None
                if row[3] is not None:
                    try:
                        payload = cPickle.loads(str(row[3]))
                    except StandardError, e:
                        print "WARNING: unpickle failed for event %d: %s" % (row[0], e)
                results.append({"id": row[0], "event_type": row[1],
                                "source": row[2], "payload": payload,
                                "timestamp": row[4]})
            return results
        except Exception, e:
            raise DatabaseError("event query failed: %s" % e)

    def put_object(self, key, obj):
        """Serialise with ``cPickle`` protocol 2 and store."""
        try:
            pickled = cPickle.dumps(obj, 2)
        except StandardError, e:
            raise StorageError("cannot serialise %r: %s" % (key, e))
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO object_store (key,pickled,protocol,updated_at) "
                "VALUES (?,?,?,?)", (key, sqlite3.Binary(pickled), 2, time.time()))
            self._conn.commit()
            print "Stored object: %s (%d bytes, protocol 2)" % (key, len(pickled))
        except Exception, e:
            raise DatabaseError("put_object failed for %r: %s" % (key, e))

    def get_object(self, key):
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT pickled FROM object_store WHERE key=?", (key,))
            row = cur.fetchone()
            return cPickle.loads(str(row[0])) if row else None
        except StandardError, e:
            raise StorageError("cannot deserialise %r: %s" % (key, e))

    def purge_readings_before(self, cutoff_ts):
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff_ts,))
            deleted = cur.rowcount
            self._conn.commit()
            print "Purged %d readings older than %.0f" % (deleted, cutoff_ts)
            return deleted
        except Exception, e:
            raise DatabaseError("purge failed: %s" % e)

    def vacuum(self):
        try:
            self._conn.execute("VACUUM")
            print "VACUUM complete"
        except Exception, e:
            print "VACUUM failed (non-fatal): %s" % e
