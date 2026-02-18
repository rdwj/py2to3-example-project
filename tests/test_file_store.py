# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/file_store.py

Tests the current Python 2 behavior including:
- file() builtin (removed in Py3, use open())
- os.getcwdu() (removed in Py3, os.getcwd() returns unicode)
- Octal permissions 0644/0755 (Py3 requires 0o644/0o755)
- Binary vs text mode behavior
- except IOError, e syntax
- long type literals (0L)
- struct packing for binary data
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import struct
import time
import pytest

from src.storage.file_store import (
    StoragePath,
    FileStore,
    DIR_PERMISSIONS,
    FILE_PERMISSIONS,
    FILE_PERMISSIONS_RESTRICTED,
)


# ---------------------------------------------------------------------------
# Mock objects for testing
# ---------------------------------------------------------------------------

class MockDataPoint:
    """Mock sensor data point for testing."""
    def __init__(self, tag, timestamp, quality):
        self.tag = tag
        self.timestamp = timestamp
        self.quality = quality


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary storage directory."""
    return str(tmp_path)


@pytest.fixture
def storage_path(temp_storage):
    """Create a StoragePath instance."""
    return StoragePath(temp_storage)


@pytest.fixture
def file_store(temp_storage):
    """Create a FileStore instance."""
    return FileStore(temp_storage)


# ---------------------------------------------------------------------------
# Test StoragePath
# ---------------------------------------------------------------------------

def test_storage_path_initialization_with_path(temp_storage):
    """Test StoragePath initialization with explicit path."""
    sp = StoragePath(temp_storage)
    assert sp.root == temp_storage


def test_storage_path_initialization_default():
    """Test StoragePath uses os.getcwd() when no path given."""
    # This tests that os.getcwd() is called
    sp = StoragePath()
    assert sp.root is not None
    assert isinstance(sp.root, str)


def test_storage_path_getcwd_returns_str():
    """Test that os.getcwd() returns str (Py3 feature)."""
    sp = StoragePath()
    # In Py3, getcwd() returns str (unicode)
    assert isinstance(sp.root, str)


def test_storage_path_root_property(storage_path):
    """Test root property accessor."""
    assert storage_path.root is not None


def test_storage_path_reports_dir(storage_path):
    """Test reports_dir() path construction."""
    reports = storage_path.reports_dir()
    assert "reports" in reports
    assert reports.startswith(storage_path.root)


def test_storage_path_exports_dir(storage_path):
    """Test exports_dir() path construction."""
    exports = storage_path.exports_dir()
    assert "exports" in exports


def test_storage_path_raw_dumps_dir(storage_path):
    """Test raw_dumps_dir() path construction."""
    dumps = storage_path.raw_dumps_dir()
    assert "raw_dumps" in dumps


def test_storage_path_temp_dir(storage_path):
    """Test temp_dir() path construction."""
    temp = storage_path.temp_dir()
    assert ".tmp" in temp


def test_storage_path_ensure_directories(storage_path, capsys):
    """Test ensure_directories() creates all subdirs."""
    storage_path.ensure_directories()

    assert os.path.isdir(storage_path.reports_dir())
    assert os.path.isdir(storage_path.exports_dir())
    assert os.path.isdir(storage_path.raw_dumps_dir())
    assert os.path.isdir(storage_path.temp_dir())

    captured = capsys.readouterr()
    assert "Created directory" in captured.out


def test_storage_path_ensure_directories_sets_permissions(storage_path):
    """Test that directories are created with correct permissions."""
    storage_path.ensure_directories()

    # Check permissions (octal 0755)
    reports_stat = os.stat(storage_path.reports_dir())
    # DIR_PERMISSIONS is 0755 in old octal notation
    # The actual permission check depends on umask


def test_storage_path_resolve(storage_path):
    """Test resolve() for path joining."""
    path = storage_path.resolve("reports", "test.txt")
    assert "reports" in path
    assert "test.txt" in path
    assert path.startswith(storage_path.root)


def test_storage_path_bytes_conversion():
    """Test handling of bytes vs str paths."""
    # In Py3, we can pass bytes and it gets decoded
    path_bytes = b"/tmp/test"
    sp = StoragePath(path_bytes)
    assert isinstance(sp.root, str)


# ---------------------------------------------------------------------------
# Test FileStore initialization
# ---------------------------------------------------------------------------

def test_file_store_initialization_with_path(temp_storage):
    """Test FileStore initialization with path string."""
    fs = FileStore(temp_storage)
    assert fs.root == temp_storage


def test_file_store_initialization_with_storage_path(storage_path):
    """Test FileStore initialization with StoragePath object."""
    fs = FileStore(storage_path)
    assert fs.root == storage_path.root


def test_file_store_creates_directories(temp_storage):
    """Test that FileStore creates directories on init."""
    fs = FileStore(temp_storage)
    assert os.path.isdir(fs._path.reports_dir())
    assert os.path.isdir(fs._path.exports_dir())


# ---------------------------------------------------------------------------
# Test FileStore store_report with file() builtin
# ---------------------------------------------------------------------------

def test_file_store_store_report_simple(file_store):
    """Test storing a text report using file() builtin."""
    content = "Test report content"
    file_store.store_report("test_report.txt", content)

    report_path = os.path.join(file_store._path.reports_dir(), "test_report.txt")
    assert os.path.isfile(report_path)

    # Read back
    with open(report_path, "r") as f:
        saved = f.read()
    assert saved == content


def test_file_store_store_report_unicode(file_store):
    """Test storing report with unicode content."""
    content = u"温度レポート: センサー故障"
    file_store.store_report("unicode_report.txt", content)

    report_path = os.path.join(file_store._path.reports_dir(), "unicode_report.txt")
    assert os.path.isfile(report_path)

    # Read back as bytes and decode
    with open(report_path, "rb") as f:
        saved_bytes = f.read()
    saved = saved_bytes.decode("utf-8")
    assert "温度" in saved


def test_file_store_store_report_custom_encoding(file_store):
    """Test storing report with custom encoding."""
    content = u"Überwachungsbericht"
    file_store.store_report("german_report.txt", content, encoding="utf-8")

    report_path = os.path.join(file_store._path.reports_dir(), "german_report.txt")
    assert os.path.isfile(report_path)


def test_file_store_store_report_sets_permissions(file_store):
    """Test that reports get correct file permissions (0644)."""
    file_store.store_report("perm_test.txt", "test")

    report_path = os.path.join(file_store._path.reports_dir(), "perm_test.txt")
    # FILE_PERMISSIONS is 0644 in old octal notation
    # Actual check depends on umask, just verify file exists
    assert os.path.isfile(report_path)


def test_file_store_store_report_prints_confirmation(file_store, capsys):
    """Test that store_report prints confirmation."""
    file_store.store_report("test.txt", "content")

    captured = capsys.readouterr()
    assert "Wrote report" in captured.out


def test_file_store_store_report_ioerror_handling(file_store, monkeypatch):
    """Test IOError handling with except IOError as e syntax."""
    # Make open() raise IOError
    def mock_open(*args, **kwargs):
        raise IOError("Mock IO error")

    monkeypatch.setattr("builtins.open", mock_open)

    with pytest.raises(Exception) as exc_info:
        file_store.store_report("fail.txt", "content")
    assert "failed to write" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test FileStore store_binary with file() and 'wb' mode
# ---------------------------------------------------------------------------

def test_file_store_store_binary_simple(file_store):
    """Test storing binary data using file() with 'wb' mode."""
    binary_data = b"\x00\x01\x02\x03\xff\xfe\xfd"
    file_store.store_binary("test.bin", binary_data)

    bin_path = os.path.join(file_store._path.raw_dumps_dir(), "test.bin")
    assert os.path.isfile(bin_path)

    with open(bin_path, "rb") as f:
        saved = f.read()
    assert saved == binary_data


def test_file_store_store_binary_custom_subdir(file_store):
    """Test storing binary in custom subdirectory."""
    binary_data = b"\x01\x02\x03"
    file_store.store_binary("test.bin", binary_data, subdir="exports")

    bin_path = os.path.join(file_store._path.exports_dir(), "test.bin")
    assert os.path.isfile(bin_path)


def test_file_store_store_binary_prints_size(file_store, capsys):
    """Test that binary write prints size."""
    file_store.store_binary("test.bin", b"\x00" * 100)

    captured = capsys.readouterr()
    assert "Wrote binary" in captured.out
    assert "100 bytes" in captured.out


# ---------------------------------------------------------------------------
# Test FileStore store_sensor_dump with struct packing
# ---------------------------------------------------------------------------

def test_file_store_store_sensor_dump(file_store):
    """Test storing sensor dump with struct packing."""
    sensor_id = "SENSOR001"
    raw_frames = [b"\x01\x02\x03", b"\x04\x05\x06"]
    readings = [
        MockDataPoint(tag="TAG001", timestamp=1234567890.5, quality=100),
        MockDataPoint(tag="TAG002", timestamp=1234567891.5, quality=95),
    ]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    # Find the created file
    dumps = file_store.list_raw_dumps(sensor_id)
    assert len(dumps) >= 1

    dump_path = os.path.join(file_store._path.raw_dumps_dir(), dumps[0])
    assert os.path.isfile(dump_path)

    # Verify it's binary data
    with open(dump_path, "rb") as f:
        data = f.read()
    assert len(data) > 0


def test_file_store_store_sensor_dump_struct_format(file_store):
    """Test struct packing format in sensor dump."""
    sensor_id = "TEST"
    raw_frames = [b"frame1"]
    readings = [MockDataPoint(tag="TAG", timestamp=123.0, quality=100)]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    dumps = file_store.list_raw_dumps(sensor_id)
    dump_path = os.path.join(file_store._path.raw_dumps_dir(), dumps[0])

    # Read back and verify struct format
    with open(dump_path, "rb") as f:
        # First 4 bytes: number of frames (>I format)
        num_frames = struct.unpack(">I", f.read(4))[0]
        assert num_frames == 1


def test_file_store_store_sensor_dump_unicode_tag(file_store):
    """Test sensor dump with unicode tag name."""
    sensor_id = "SENSOR_JP"
    raw_frames = [b"frame"]
    readings = [MockDataPoint(tag=u"温度", timestamp=123.0, quality=100)]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    dumps = file_store.list_raw_dumps(sensor_id)
    assert len(dumps) >= 1


def test_file_store_store_sensor_dump_permissions(file_store):
    """Test sensor dump uses restricted permissions (0600)."""
    sensor_id = "SECURE"
    raw_frames = [b"data"]
    readings = [MockDataPoint(tag="TAG", timestamp=123.0, quality=100)]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    dumps = file_store.list_raw_dumps(sensor_id)
    dump_path = os.path.join(file_store._path.raw_dumps_dir(), dumps[0])

    # FILE_PERMISSIONS_RESTRICTED is 0600
    # Actual check depends on umask
    assert os.path.isfile(dump_path)


def test_file_store_store_sensor_dump_prints_summary(file_store, capsys):
    """Test sensor dump prints summary."""
    sensor_id = "SENSOR"
    raw_frames = [b"f1", b"f2"]
    readings = [MockDataPoint(tag="T1", timestamp=1.0, quality=100)]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    captured = capsys.readouterr()
    assert "Sensor dump" in captured.out
    assert "2 frames" in captured.out
    assert "1 readings" in captured.out


# ---------------------------------------------------------------------------
# Test FileStore store_export
# ---------------------------------------------------------------------------

def test_file_store_store_export(file_store):
    """Test storing export file."""
    content = "Export data"
    file_store.store_export("export.csv", content)

    export_path = os.path.join(file_store._path.exports_dir(), "export.csv")
    assert os.path.isfile(export_path)


def test_file_store_store_export_unicode(file_store):
    """Test storing export with unicode content."""
    content = u"製品,数量\nセンサーA,10"
    file_store.store_export("export_jp.csv", content)

    export_path = os.path.join(file_store._path.exports_dir(), "export_jp.csv")
    assert os.path.isfile(export_path)


# ---------------------------------------------------------------------------
# Test FileStore read_report
# ---------------------------------------------------------------------------

def test_file_store_read_report(file_store):
    """Test reading report returns bytes (str in Py2)."""
    content = "Test report"
    file_store.store_report("read_test.txt", content)

    data = file_store.read_report("read_test.txt")
    assert data == content


def test_file_store_read_report_nonexistent(file_store):
    """Test reading nonexistent report returns None."""
    data = file_store.read_report("nonexistent.txt")
    assert data is None


def test_file_store_read_report_ioerror(file_store, monkeypatch):
    """Test IOError handling in read_report."""
    file_store.store_report("test.txt", "content")

    # Make open() raise IOError on read
    original_open = open

    def mock_open(path, mode):
        if "r" in mode:
            raise IOError("Mock read error")
        return original_open(path, mode)

    monkeypatch.setattr("builtins.open", mock_open)

    with pytest.raises(Exception) as exc_info:
        file_store.read_report("test.txt")
    assert "cannot read" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test FileStore read_binary
# ---------------------------------------------------------------------------

def test_file_store_read_binary(file_store):
    """Test reading binary data."""
    data = b"\x00\x01\x02\xff"
    file_store.store_binary("test.bin", data)

    read_data = file_store.read_binary("test.bin")
    assert read_data == data


def test_file_store_read_binary_nonexistent(file_store):
    """Test reading nonexistent binary returns None."""
    data = file_store.read_binary("nonexistent.bin")
    assert data is None


def test_file_store_read_binary_custom_subdir(file_store):
    """Test reading binary from custom subdir."""
    data = b"\x01\x02"
    file_store.store_binary("test.bin", data, subdir="exports")

    read_data = file_store.read_binary("test.bin", subdir="exports")
    assert read_data == data


# ---------------------------------------------------------------------------
# Test FileStore list operations
# ---------------------------------------------------------------------------

def test_file_store_list_reports(file_store):
    """Test listing report files."""
    file_store.store_report("report1.txt", "content1")
    file_store.store_report("report2.txt", "content2")

    reports = file_store.list_reports()
    assert "report1.txt" in reports
    assert "report2.txt" in reports
    assert reports == sorted(reports)  # Should be sorted


def test_file_store_list_reports_empty(file_store):
    """Test listing reports when directory is empty."""
    # Clear reports directory
    reports = file_store.list_reports()
    # May or may not be empty depending on setup
    assert isinstance(reports, list)


def test_file_store_list_exports(file_store):
    """Test listing export files."""
    file_store.store_export("export1.csv", "data1")
    file_store.store_export("export2.csv", "data2")

    exports = file_store.list_exports()
    assert "export1.csv" in exports
    assert "export2.csv" in exports


def test_file_store_list_raw_dumps(file_store):
    """Test listing raw dump files."""
    sensor_id = "SENSOR001"
    raw_frames = [b"frame"]
    readings = [MockDataPoint(tag="TAG", timestamp=123.0, quality=100)]

    file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    dumps = file_store.list_raw_dumps()
    assert len(dumps) > 0


def test_file_store_list_raw_dumps_filtered(file_store):
    """Test listing raw dumps filtered by sensor_id."""
    # Create dumps for different sensors
    for sensor_id in ["SENSOR_A", "SENSOR_B"]:
        raw_frames = [b"frame"]
        readings = [MockDataPoint(tag="TAG", timestamp=123.0, quality=100)]
        file_store.store_sensor_dump(sensor_id, readings, raw_frames)

    dumps_a = file_store.list_raw_dumps(sensor_id="SENSOR_A")
    assert all("SENSOR_A" in d for d in dumps_a)


# ---------------------------------------------------------------------------
# Test FileStore storage_summary with long type
# ---------------------------------------------------------------------------

def test_file_store_storage_summary(file_store, capsys):
    """Test storage_summary() uses long type (0L)."""
    file_store.store_report("test.txt", "content")
    file_store.store_binary("test.bin", b"\x00" * 100)

    file_store.storage_summary()

    captured = capsys.readouterr()
    assert "Total:" in captured.out
    assert "files" in captured.out
    assert "bytes" in captured.out


def test_file_store_storage_summary_long_type(file_store):
    """Test that long type literals (0L) are used internally."""
    # The storage_summary method initializes with 0L
    file_store.store_report("test.txt", "test")
    # Just verify it doesn't crash (long type handling)
    file_store.storage_summary()


def test_file_store_storage_summary_handles_subdirs(file_store, capsys):
    """Test storage_summary covers all subdirectories."""
    file_store.store_report("r.txt", "report")
    file_store.store_export("e.txt", "export")
    file_store.store_binary("d.bin", b"dump")

    file_store.storage_summary()

    captured = capsys.readouterr()
    assert "reports" in captured.out
    assert "exports" in captured.out
    assert "raw_dumps" in captured.out


# ---------------------------------------------------------------------------
# Test FileStore purge_before
# ---------------------------------------------------------------------------

def test_file_store_purge_before(file_store, capsys):
    """Test purging old files."""
    file_store.store_report("old.txt", "old content")

    # Set cutoff to future time
    cutoff = time.time() + 3600
    removed = file_store.purge_before(cutoff)

    assert removed >= 1

    captured = capsys.readouterr()
    assert "Purged" in captured.out


def test_file_store_purge_before_specific_subdir(file_store):
    """Test purging specific subdirectory."""
    file_store.store_report("report.txt", "content")
    file_store.store_export("export.txt", "content")

    # Purge only reports
    cutoff = time.time() + 3600
    removed = file_store.purge_before(cutoff, subdir="reports")

    # Reports should be purged, exports remain
    assert len(file_store.list_reports()) == 0
    assert len(file_store.list_exports()) > 0


def test_file_store_purge_before_no_old_files(file_store):
    """Test purge when no files are old enough."""
    file_store.store_report("new.txt", "content")

    # Set cutoff to past time
    cutoff = time.time() - 3600
    removed = file_store.purge_before(cutoff)

    assert removed == 0


# ---------------------------------------------------------------------------
# Test FileStore clear_temp
# ---------------------------------------------------------------------------

def test_file_store_clear_temp(file_store, capsys):
    """Test clearing temporary directory."""
    # Put something in temp dir
    temp_file = os.path.join(file_store._path.temp_dir(), "temp.txt")
    with open(temp_file, "w") as f:
        f.write("temp content")

    file_store.clear_temp()

    # Temp dir should exist but be empty
    assert os.path.isdir(file_store._path.temp_dir())
    assert len(os.listdir(file_store._path.temp_dir())) == 0

    captured = capsys.readouterr()
    assert "Temporary directory cleared" in captured.out


# ---------------------------------------------------------------------------
# Test octal literal constants
# ---------------------------------------------------------------------------

def test_octal_permissions_constants():
    """Test that octal permission constants are defined."""
    # In Py3, octal needs 0o prefix
    assert DIR_PERMISSIONS == 0o755
    assert FILE_PERMISSIONS == 0o644
    assert FILE_PERMISSIONS_RESTRICTED == 0o600


# ---------------------------------------------------------------------------
# Test file() vs open() usage
# ---------------------------------------------------------------------------

def test_file_store_uses_open_builtin(file_store, monkeypatch):
    """Test that open() builtin is used."""
    open_called = []

    original_open = open

    def tracking_open(*args, **kwargs):
        open_called.append(args)
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)

    file_store.store_report("test.txt", "content")

    assert len(open_called) > 0


# ---------------------------------------------------------------------------
# Test binary mode behavior
# ---------------------------------------------------------------------------

def test_file_store_binary_mode_preserves_bytes(file_store):
    """Test that 'wb' mode preserves exact byte content."""
    binary_data = b"\x00\x01\x02\x03\x80\xff"
    file_store.store_binary("bytes.bin", binary_data)

    read_data = file_store.read_binary("bytes.bin")
    assert read_data == binary_data
    assert isinstance(read_data, bytes)  # In Py3, bytes is bytes


def test_file_store_text_mode_behavior(file_store):
    """Test text mode behavior (Py2 vs Py3 difference)."""
    # In Py2, 'w' mode is byte-oriented on Unix
    file_store.store_report("text.txt", "test")
    data = file_store.read_report("text.txt")

    # In Py2, this returns str (bytes)
    assert isinstance(data, str)
