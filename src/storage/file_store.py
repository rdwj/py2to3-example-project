# -*- coding: utf-8 -*-
"""
File-based storage for the Legacy Industrial Data Platform.

Handles processed reports, exported data, and binary sensor dumps on
the local filesystem.
"""


import os
import time
import struct
import shutil

from src.core.exceptions import StorageError

_DIR_REPORTS = "reports"
_DIR_EXPORTS = "exports"
_DIR_RAW_DUMPS = "raw_dumps"
_DIR_TEMP = ".tmp"

# Octal literals use 0o prefix in Python 3
DIR_PERMISSIONS = 0o755
FILE_PERMISSIONS = 0o644
FILE_PERMISSIONS_RESTRICTED = 0o600


class StoragePath:
    """Path wrapper.  In Py3, ``os.getcwd()`` already returns str (text)."""

    def __init__(self, root_path=None):
        if root_path is None:
            root_path = os.getcwd()
        self._root = os.path.abspath(root_path)

    @property
    def root(self):
        return self._root

    def reports_dir(self):
        return os.path.join(self._root, _DIR_REPORTS)

    def exports_dir(self):
        return os.path.join(self._root, _DIR_EXPORTS)

    def raw_dumps_dir(self):
        return os.path.join(self._root, _DIR_RAW_DUMPS)

    def temp_dir(self):
        return os.path.join(self._root, _DIR_TEMP)

    def ensure_directories(self):
        for d in (self.reports_dir(), self.exports_dir(),
                  self.raw_dumps_dir(), self.temp_dir()):
            if not os.path.isdir(d):
                os.makedirs(d)
                os.chmod(d, DIR_PERMISSIONS)
                print(f"Created directory: {d}")

    def resolve(self, *parts):
        return os.path.join(self._root, *parts)


class FileStore:
    """Read/write data files.  Binary data uses ``'wb'``; text uses
    ``'w'``."""

    def __init__(self, storage_path=None):
        if isinstance(storage_path, StoragePath):
            self._path = storage_path
        else:
            self._path = StoragePath(storage_path)
        self._path.ensure_directories()

    @property
    def root(self):
        return self._path.root

    def store_report(self, filename, content, encoding="utf-8"):
        """Write text report."""
        dest = self._path.resolve(_DIR_REPORTS, filename)
        try:
            with open(dest, "w", encoding=encoding) as f:
                f.write(content)
            os.chmod(dest, FILE_PERMISSIONS)
            print(f"Wrote report: {dest} ({os.path.getsize(dest)} bytes)")
        except IOError as e:
            raise StorageError(f"failed to write report {filename}: {e}")

    def store_binary(self, filename, data, subdir=None):
        """Write raw binary data in ``'wb'`` mode."""
        dest = self._path.resolve(subdir or _DIR_RAW_DUMPS, filename)
        try:
            with open(dest, "wb") as f:
                f.write(data)
            os.chmod(dest, FILE_PERMISSIONS)
            print(f"Wrote binary: {dest} ({len(data)} bytes)")
        except IOError as e:
            raise StorageError(f"failed to write binary {filename}: {e}")

    def store_sensor_dump(self, sensor_id, readings, raw_frames):
        """Combined dump: length-prefixed raw frames + reading fields."""
        fname = f"{sensor_id}_{time.strftime('%Y%m%d_%H%M%S')}.dump"
        dest = self._path.resolve(_DIR_RAW_DUMPS, fname)
        try:
            with open(dest, "wb") as f:
                f.write(struct.pack(">I", len(raw_frames)))
                for frame in raw_frames:
                    f.write(struct.pack(">I", len(frame)))
                    f.write(frame)
                f.write(struct.pack(">I", len(readings)))
                for dp in readings:
                    tag = dp.tag.encode("utf-8") if isinstance(dp.tag, str) else dp.tag
                    f.write(struct.pack(">H", len(tag)))
                    f.write(tag)
                    f.write(struct.pack(">dI", dp.timestamp, dp.quality))
            os.chmod(dest, FILE_PERMISSIONS_RESTRICTED)
            print(f"Sensor dump: {fname} ({len(raw_frames)} frames, {len(readings)} readings)")
        except (IOError, struct.error) as e:
            raise StorageError(f"sensor dump failed for {sensor_id}: {e}")

    def store_export(self, filename, content, encoding="utf-8"):
        dest = self._path.resolve(_DIR_EXPORTS, filename)
        try:
            with open(dest, "w", encoding=encoding) as f:
                f.write(content)
            os.chmod(dest, FILE_PERMISSIONS)
            print(f"Wrote export: {dest}")
        except IOError as e:
            raise StorageError(f"export failed for {filename}: {e}")

    def read_report(self, filename, encoding="utf-8"):
        """Returns the report content as a string, decoded with the
        given *encoding* (default ``'utf-8'``).  Callers that wrote
        with a non-UTF-8 encoding must pass the matching encoding here
        to avoid ``UnicodeDecodeError``."""
        src = self._path.resolve(_DIR_REPORTS, filename)
        if not os.path.isfile(src):
            return None
        try:
            with open(src, "r", encoding=encoding) as f:
                return f.read()
        except IOError as e:
            raise StorageError(f"cannot read report {filename}: {e}")

    def read_binary(self, filename, subdir=None):
        src = self._path.resolve(subdir or _DIR_RAW_DUMPS, filename)
        if not os.path.isfile(src):
            return None
        try:
            with open(src, "rb") as f:
                return f.read()
        except IOError as e:
            raise StorageError(f"cannot read binary {filename}: {e}")

    def list_reports(self):
        d = self._path.reports_dir()
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def list_exports(self):
        d = self._path.exports_dir()
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def list_raw_dumps(self, sensor_id=None):
        d = self._path.raw_dumps_dir()
        if not os.path.isdir(d):
            return []
        entries = os.listdir(d)
        if sensor_id is not None:
            entries = [e for e in entries if e.startswith(sensor_id + "_")]
        return sorted(entries)

    def storage_summary(self):
        total_bytes, total_files = 0, 0
        for name in (_DIR_REPORTS, _DIR_EXPORTS, _DIR_RAW_DUMPS):
            d = self._path.resolve(name)
            if not os.path.isdir(d):
                continue
            files = os.listdir(d)
            nbytes = sum(os.path.getsize(os.path.join(d, f))
                         for f in files if os.path.isfile(os.path.join(d, f)))
            total_files += len(files)
            total_bytes += nbytes
            print(f"  {name:<12}  {len(files):4d} files  {nbytes:10d} bytes")
        print(f"  Total: {total_files} files, {total_bytes} bytes")

    def purge_before(self, cutoff_ts, subdir=None):
        """Delete files modified before *cutoff_ts*."""
        if subdir is not None:
            dirs = [self._path.resolve(subdir)]
        else:
            dirs = [self._path.reports_dir(), self._path.exports_dir(),
                    self._path.raw_dumps_dir()]
        removed = 0
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff_ts:
                    os.remove(p)
                    removed += 1
        print(f"Purged {removed} files older than {cutoff_ts:.0f}")
        return removed

    def clear_temp(self):
        t = self._path.temp_dir()
        if os.path.isdir(t):
            shutil.rmtree(t)
            os.makedirs(t)
            os.chmod(t, DIR_PERMISSIONS)
            print("Temporary directory cleared")
