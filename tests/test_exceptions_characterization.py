# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/exceptions.py

Captures pre-migration behavior of:
- PlatformError inheriting from StandardError (renamed Exception in Py3)
- Exception hierarchy (Protocol, Data, Storage layers)
- capture_exc_info using sys.exc_type/sys.exc_value (removed in Py3)
- reraise_with_context using 3-arg raise (changed in Py3)
- safe_execute with except comma syntax
- format_current_exception using legacy sys attributes
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.exceptions import (
    PlatformError, ProtocolError, ModbusError, SerialError,
    MqttError, OpcUaError, DataError, EncodingError, ParseError,
    ValidationError, StorageError, DatabaseError, CacheError,
    capture_exc_info, reraise_with_context, safe_execute,
    wrap_protocol_error, format_current_exception,
)


class TestExceptionHierarchy:
    """Characterize the exception class hierarchy."""

    @pytest.mark.py2_behavior
    def test_platform_error_inherits_exception(self):
        """Captures: PlatformError(Exception). StandardError was merged into
        Exception in Py3."""
        assert issubclass(PlatformError, Exception)

    def test_protocol_layer(self):
        """Captures: protocol exceptions inherit from PlatformError."""
        assert issubclass(ProtocolError, PlatformError)
        assert issubclass(ModbusError, ProtocolError)
        assert issubclass(SerialError, ProtocolError)
        assert issubclass(MqttError, ProtocolError)
        assert issubclass(OpcUaError, ProtocolError)

    def test_data_layer(self):
        """Captures: data exceptions inherit from PlatformError."""
        assert issubclass(DataError, PlatformError)
        assert issubclass(EncodingError, DataError)
        assert issubclass(ParseError, DataError)
        assert issubclass(ValidationError, DataError)

    def test_storage_layer(self):
        """Captures: storage exceptions inherit from PlatformError."""
        assert issubclass(StorageError, PlatformError)
        assert issubclass(DatabaseError, StorageError)
        assert issubclass(CacheError, StorageError)

    def test_platform_error_code(self):
        """Captures: PlatformError accepts optional code parameter."""
        err = PlatformError("test error", code=42)
        assert str(err) == "test error"
        assert err.code == 42

    def test_modbus_error_fields(self):
        """Captures: ModbusError has function_code and exception_code."""
        err = ModbusError("timeout", function_code=3, exception_code=4)
        assert err.function_code == 3
        assert err.exception_code == 4


class TestExceptionUtilities:
    """Characterize exception handling utilities."""

    @pytest.mark.py2_behavior
    def test_capture_exc_info(self):
        """Captures: sys.exc_type and sys.exc_value (G2).
        Removed in Py3; use sys.exc_info()."""
        try:
            raise ValueError("test")
        except ValueError:
            exc_type, exc_value = capture_exc_info()
            assert exc_type is ValueError
            assert str(exc_value) == "test"

    @pytest.mark.py2_behavior
    def test_format_current_exception(self):
        """Captures: format string using sys.exc_type.__name__ and sys.exc_value."""
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            msg = format_current_exception()
            assert "RuntimeError" in msg
            assert "boom" in msg

    @pytest.mark.py2_behavior
    def test_safe_execute_success(self):
        """Captures: safe_execute returns function result on success."""
        result = safe_execute(lambda: 42)
        assert result == 42

    @pytest.mark.py2_behavior
    def test_safe_execute_wraps_exception(self):
        """Captures: non-PlatformError wrapped in PlatformError.
        Uses except comma syntax and 2-arg raise."""
        with pytest.raises(PlatformError, match="Unexpected error"):
            safe_execute(lambda: 1/0)

    @pytest.mark.py2_behavior
    def test_safe_execute_passes_platform_error(self):
        """Captures: PlatformError raised as-is, not wrapped."""
        def fn():
            raise PlatformError("direct")
        with pytest.raises(PlatformError, match="direct"):
            safe_execute(fn)

    @pytest.mark.py2_behavior
    def test_reraise_with_context(self):
        """Captures: 3-arg raise form: raise ExcClass, value, traceback.
        Changed to raise ExcClass(value).with_traceback(tb) in Py3."""
        with pytest.raises(DatabaseError):
            try:
                raise ValueError("original")
            except ValueError:
                reraise_with_context(DatabaseError, "wrapped error")

    @pytest.mark.py2_behavior
    def test_wrap_protocol_error(self):
        """Captures: wraps EnvironmentError in ProtocolError."""
        def fn():
            raise IOError("connection reset")
        with pytest.raises(ProtocolError, match="I/O error"):
            wrap_protocol_error(fn)
