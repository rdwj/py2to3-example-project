# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/file_store.py

Captures pre-migration behavior of:
- StoragePath directory resolution and os.getcwdu()
- FileStore read/write for text reports and binary data
- file() builtin (removed in Py3; use open())
- Octal literals 0755/0644 (Py3 requires 0o755/0o644)
- unicode/str isinstance checks for encoding decisions
- long() for storage_summary byte counting
- struct.pack for sensor dump binary format
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.storage.file_store import StoragePath, FileStore, DIR_PERMISSIONS, FILE_PERMISSIONS


# ---------------------------------------------------------------------------
# StoragePath
# ---------------------------------------------------------------------------

class TestStoragePath:
    """Characterize path resolution and directory management."""

    def test_root_from_explicit_path(self, tmp_path):
        """Captures: StoragePath accepts an explicit root path."""
        sp = StoragePath(str(tmp_path))
        assert sp.root == os.path.abspath(str(tmp_path))

    def test_reports_dir(self, tmp_path):
        """Captures: reports_dir joins root with 'reports'."""
        sp = StoragePath(str(tmp_path))
        assert sp.reports_dir().endswith("reports")

    def test_exports_dir(self, tmp_path):
        """Captures: exports_dir joins root with 'exports'."""
        sp = StoragePath(str(tmp_path))
        assert sp.exports_dir().endswith("exports")

    def test_raw_dumps_dir(self, tmp_path):
        """Captures: raw_dumps_dir joins root with 'raw_dumps'."""
        sp = StoragePath(str(tmp_path))
        assert sp.raw_dumps_dir().endswith("raw_dumps")

    def test_temp_dir(self, tmp_path):
        """Captures: temp_dir joins root with '.tmp'."""
        sp = StoragePath(str(tmp_path))
        assert sp.temp_dir().endswith(".tmp")

    def test_ensure_directories_creates_all(self, tmp_path):
        """Captures: ensure_directories creates all subdirectories."""
        sp = StoragePath(str(tmp_path))
        sp.ensure_directories()
        assert os.path.isdir(sp.reports_dir())
        assert os.path.isdir(sp.exports_dir())
        assert os.path.isdir(sp.raw_dumps_dir())
        assert os.path.isdir(sp.temp_dir())

    def test_resolve_joins_parts(self, tmp_path):
        """Captures: resolve joins root with arbitrary path parts."""
        sp = StoragePath(str(tmp_path))
        result = sp.resolve("subdir", "file.txt")
        assert result == os.path.join(str(tmp_path), "subdir", "file.txt")


# ---------------------------------------------------------------------------
# FileStore -- text operations
# ---------------------------------------------------------------------------

class TestFileStoreText:
    """Characterize text file read/write operations."""

    @pytest.fixture
    def store(self, tmp_path):
        return FileStore(str(tmp_path))

    @pytest.mark.py2_behavior
    def test_store_report_ascii(self, store):
        """Captures: store_report writes text via file() builtin.
        file() removed in Py3; use open()."""
        store.store_report("test.txt", "Hello World")
        content = store.read_report("test.txt")
        assert content is not None
        assert "Hello World" in content

    @pytest.mark.py2_behavior
    def test_store_report_unicode_encoded(self, store):
        """Captures: unicode content written as text in Py3.
        read_report returns str (text) in Py3, not bytes."""
        store.store_report("unicode.txt", u"caf\u00e9 r\u00e9sum\u00e9")
        content = store.read_report("unicode.txt")
        assert content is not None
        # In Py3, read_report returns str (text)
        assert "caf" in content

    def test_read_report_nonexistent_returns_none(self, store):
        """Captures: reading a missing file returns None."""
        assert store.read_report("missing.txt") is None

    def test_store_export(self, store):
        """Captures: store_export writes to exports directory."""
        store.store_export("export.csv", "tag,value\nTEMP,23.5")
        exports = store.list_exports()
        assert "export.csv" in exports

    def test_list_reports(self, store):
        """Captures: list_reports returns sorted filenames."""
        store.store_report("b.txt", "B")
        store.store_report("a.txt", "A")
        reports = store.list_reports()
        assert reports == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# FileStore -- binary operations
# ---------------------------------------------------------------------------

class TestFileStoreBinary:
    """Characterize binary file read/write operations."""

    @pytest.fixture
    def store(self, tmp_path):
        return FileStore(str(tmp_path))

    def test_store_and_read_binary(self, store):
        """Captures: binary round-trip with high bytes."""
        data = b"\x00\x01\x7F\x80\xFF\xAA\x55"
        store.store_binary("test.bin", data)
        result = store.read_binary("test.bin")
        assert result == data

    def test_read_binary_nonexistent_returns_none(self, store):
        """Captures: reading a missing binary file returns None."""
        assert store.read_binary("missing.bin") is None

    def test_list_raw_dumps(self, store):
        """Captures: list_raw_dumps returns sorted filenames."""
        store.store_binary("dump_a.bin", b"\x01")
        store.store_binary("dump_b.bin", b"\x02")
        dumps = store.list_raw_dumps()
        assert dumps == ["dump_a.bin", "dump_b.bin"]

    def test_list_raw_dumps_filtered_by_sensor_id(self, store):
        """Captures: sensor_id prefix filter on dump listing."""
        store.store_binary("S001_20240101.dump", b"\x01")
        store.store_binary("S002_20240101.dump", b"\x02")
        filtered = store.list_raw_dumps(sensor_id="S001")
        assert len(filtered) == 1
        assert "S001" in filtered[0]

    @pytest.mark.py2_behavior
    def test_store_sensor_dump_binary_format(self, store):
        """Captures: sensor dump with struct-packed length prefixes.
        Uses struct.pack('>I', len), struct.pack('>H', len), struct.pack('>dI', ts, q)."""
        from src.core.types import DataPoint
        frames = [b"\xAA\x08\x00\x01\x01\x00\xEB\x42"]
        readings = [DataPoint("TEMP-001", 23.5, timestamp=1000.0, quality=192)]
        store.store_sensor_dump("S001", readings, frames)
        dumps = store.list_raw_dumps(sensor_id="S001")
        assert len(dumps) == 1


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestFileStoreEncodingBoundaries:
    """Test encoding edge cases in file operations."""

    @pytest.fixture
    def store(self, tmp_path):
        return FileStore(str(tmp_path))

    @pytest.mark.py2_behavior
    def test_store_report_latin1_encoding(self, store):
        """Captures: store_report with explicit latin-1 encoding."""
        store.store_report("latin.txt", u"\u00e9\u00e8\u00ea", encoding="latin-1")
        content = store.read_report("latin.txt", encoding="latin-1")
        assert content is not None
        # In Py3, read_report returns str (text); verify the accented chars
        assert u"\u00e9" in content

    @pytest.mark.py2_behavior
    def test_store_binary_with_null_bytes(self, store):
        """Captures: binary storage handles embedded null bytes."""
        data = b"\x00" * 100 + b"\xFF" * 100
        store.store_binary("nulls.bin", data)
        result = store.read_binary("nulls.bin")
        assert result == data

    def test_purge_before_removes_old_files(self, store):
        """Captures: purge_before deletes files older than cutoff."""
        store.store_report("old.txt", "old content")
        # Files just written have mtime ~ now
        # Set cutoff far in the future to delete everything
        import time
        removed = store.purge_before(time.time() + 100.0)
        assert removed >= 1
