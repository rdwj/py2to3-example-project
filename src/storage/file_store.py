# -*- coding: utf-8 -*-
"""
File-based storage for the Legacy Industrial Data Platform.

Handles processed reports, exported data, and binary sensor dumps on
the local filesystem.  Uses Python 2-specific APIs:
- ``file()`` builtin (removed in Py3; use ``open()``)
- ``os.getcwdu()`` for unicode cwd (Py3 ``os.getcwd()`` returns text)
- Octal literals ``0644`` (Py3 requires ``0o644``)
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import time
import struct
import shutil

from src.core.exceptions import StorageError

_DIR_REPORTS = "reports"
_DIR_EXPORTS = "exports"
_DIR_RAW_DUMPS = "raw_dumps"
_DIR_TEMP = ".tmp"

# Old-style octal -- Py3 requires 0o755/0o644 prefix form
DIR_PERMISSIONS = 0755
FILE_PERMISSIONS = 0644
FILE_PERMISSIONS_RESTRICTED = 0600


class StoragePath(object):
    """Path wrapper using ``os.getcwdu()`` for unicode resolution.
    In Py3, ``os.getcwd()`` already returns text and ``getcwdu``
    does not exist."""

    def __init__(self, root_path=None):
        if root_path is None:
            root_path = os.getcwdu()
        if isinstance(root_path, str):
            root_path = root_path.decode("utf-8")
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
                print "Created directory: %s" % d

    def resolve(self, *parts):
        return os.path.join(self._root, *parts)


class FileStore(object):
    """Read/write data files.  Binary data uses ``'wb'``; text uses
    ``'w'``.  In Py2 both are byte-oriented on Unix, but the
    convention aids the Py3 port where modes control bytes vs text."""

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
        """Write text report via ``file()`` builtin (removed in Py3)."""
        dest = self._path.resolve(_DIR_REPORTS, filename)
        try:
            f = file(dest, "w")
            try:
                if isinstance(content, unicode):
                    content = content.encode(encoding)
                f.write(content)
            finally:
                f.close()
            os.chmod(dest, FILE_PERMISSIONS)
            print "Wrote report: %s (%d bytes)" % (dest, os.path.getsize(dest))
        except IOError, e:
            raise StorageError("failed to write report %s: %s" % (filename, e))

    def store_binary(self, filename, data, subdir=None):
        """Write raw binary data in ``'wb'`` mode."""
        dest = self._path.resolve(subdir or _DIR_RAW_DUMPS, filename)
        try:
            f = file(dest, "wb")
            try:
                f.write(data)
            finally:
                f.close()
            os.chmod(dest, FILE_PERMISSIONS)
            print "Wrote binary: %s (%d bytes)" % (dest, len(data))
        except IOError, e:
            raise StorageError("failed to write binary %s: %s" % (filename, e))

    def store_sensor_dump(self, sensor_id, readings, raw_frames):
        """Combined dump: length-prefixed raw frames + reading fields."""
        fname = "%s_%s.dump" % (sensor_id, time.strftime("%Y%m%d_%H%M%S"))
        dest = self._path.resolve(_DIR_RAW_DUMPS, fname)
        try:
            f = file(dest, "wb")
            try:
                f.write(struct.pack(">I", len(raw_frames)))
                for frame in raw_frames:
                    f.write(struct.pack(">I", len(frame)))
                    f.write(frame)
                f.write(struct.pack(">I", len(readings)))
                for dp in readings:
                    tag = dp.tag.encode("utf-8") if isinstance(dp.tag, unicode) else dp.tag
                    f.write(struct.pack(">H", len(tag)))
                    f.write(tag)
                    f.write(struct.pack(">dI", dp.timestamp, dp.quality))
            finally:
                f.close()
            os.chmod(dest, FILE_PERMISSIONS_RESTRICTED)
            print "Sensor dump: %s (%d frames, %d readings)" % (
                fname, len(raw_frames), len(readings))
        except (IOError, struct.error), e:
            raise StorageError("sensor dump failed for %s: %s" % (sensor_id, e))

    def store_export(self, filename, content, encoding="utf-8"):
        dest = self._path.resolve(_DIR_EXPORTS, filename)
        try:
            f = file(dest, "w")
            try:
                if isinstance(content, unicode):
                    content = content.encode(encoding)
                f.write(content)
            finally:
                f.close()
            os.chmod(dest, FILE_PERMISSIONS)
            print "Wrote export: %s" % dest
        except IOError, e:
            raise StorageError("export failed for %s: %s" % (filename, e))

    def read_report(self, filename):
        """Returns ``str`` (bytes); caller decodes if unicode needed."""
        src = self._path.resolve(_DIR_REPORTS, filename)
        if not os.path.isfile(src):
            return None
        try:
            f = file(src, "r")
            try:
                return f.read()
            finally:
                f.close()
        except IOError, e:
            raise StorageError("cannot read report %s: %s" % (filename, e))

    def read_binary(self, filename, subdir=None):
        src = self._path.resolve(subdir or _DIR_RAW_DUMPS, filename)
        if not os.path.isfile(src):
            return None
        try:
            f = file(src, "rb")
            try:
                return f.read()
            finally:
                f.close()
        except IOError, e:
            raise StorageError("cannot read binary %s: %s" % (filename, e))

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
        total_bytes, total_files = 0L, 0
        for name in (_DIR_REPORTS, _DIR_EXPORTS, _DIR_RAW_DUMPS):
            d = self._path.resolve(name)
            if not os.path.isdir(d):
                continue
            files = os.listdir(d)
            nbytes = sum(long(os.path.getsize(os.path.join(d, f)))
                         for f in files if os.path.isfile(os.path.join(d, f)))
            total_files += len(files)
            total_bytes += nbytes
            print "  %-12s  %4d files  %10d bytes" % (name, len(files), nbytes)
        print "  Total: %d files, %d bytes" % (total_files, total_bytes)

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
        print "Purged %d files older than %.0f" % (removed, cutoff_ts)
        return removed

    def clear_temp(self):
        t = self._path.temp_dir()
        if os.path.isdir(t):
            shutil.rmtree(t)
            os.makedirs(t)
            os.chmod(t, DIR_PERMISSIONS)
            print "Temporary directory cleared"
