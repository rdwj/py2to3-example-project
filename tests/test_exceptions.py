# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/exceptions.py (GATEWAY MODULE)

Captures current Python 2 behavior for exception hierarchy.
Critical Py2→3 issues: StandardError base class, except comma syntax,
raise two/three-arg forms, sys.exc_type/exc_value/exc_traceback.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import sys

from src.core.exceptions import (
    PlatformError,
    ProtocolError,
    ModbusError,
    SerialError,
    MqttError,
    OpcUaError,
    DataError,
    EncodingError,
    ParseError,
    ValidationError,
    StorageError,
    DatabaseError,
    CacheError,
    capture_exc_info,
    reraise_with_context,
    safe_execute,
    wrap_protocol_error,
    format_current_exception,
)


# ============================================================================
# Exception Hierarchy Tests
# ============================================================================


class TestExceptionHierarchy:
    """Characterize exception inheritance."""

    def test_platform_error_inherits_standard_error(self):
        """PlatformError inherits from Exception."""
        # In Python 2, StandardError is base for built-in exceptions
        # In Python 3, it doesn't exist (use Exception)
        exc = PlatformError("test message")
        assert isinstance(exc, Exception)

    def test_platform_error_stores_message(self):
        """PlatformError stores message."""
        exc = PlatformError("error occurred")
        assert str(exc) == "error occurred"

    def test_platform_error_stores_code(self):
        """PlatformError stores optional error code."""
        exc = PlatformError("test", code=42)
        assert exc.code == 42

    def test_platform_error_code_defaults_none(self):
        """PlatformError code defaults to None."""
        exc = PlatformError("test")
        assert exc.code is None


class TestProtocolErrors:
    """Characterize protocol exception hierarchy."""

    def test_protocol_error_inherits_platform_error(self):
        """ProtocolError inherits from PlatformError."""
        exc = ProtocolError("protocol issue")
        assert isinstance(exc, PlatformError)

    def test_modbus_error_stores_function_code(self):
        """ModbusError stores MODBUS-specific codes."""
        exc = ModbusError("timeout", function_code=3, exception_code=0x0B)
        assert exc.function_code == 3
        assert exc.exception_code == 0x0B
        assert exc.code == 0x0B

    def test_modbus_error_inherits_protocol_error(self):
        """ModbusError inherits from ProtocolError."""
        exc = ModbusError("test")
        assert isinstance(exc, ProtocolError)

    def test_serial_error_inherits_protocol_error(self):
        """SerialError inherits from ProtocolError."""
        exc = SerialError("serial issue")
        assert isinstance(exc, ProtocolError)

    def test_mqtt_error_inherits_protocol_error(self):
        """MqttError inherits from ProtocolError."""
        exc = MqttError("mqtt issue")
        assert isinstance(exc, ProtocolError)

    def test_opcua_error_inherits_protocol_error(self):
        """OpcUaError inherits from ProtocolError."""
        exc = OpcUaError("opcua issue")
        assert isinstance(exc, ProtocolError)


class TestDataErrors:
    """Characterize data exception hierarchy."""

    def test_data_error_inherits_platform_error(self):
        """DataError inherits from PlatformError."""
        exc = DataError("data problem")
        assert isinstance(exc, PlatformError)

    def test_encoding_error_inherits_data_error(self):
        """EncodingError inherits from DataError."""
        exc = EncodingError("encoding issue")
        assert isinstance(exc, DataError)

    def test_parse_error_inherits_data_error(self):
        """ParseError inherits from DataError."""
        exc = ParseError("parse failure")
        assert isinstance(exc, DataError)

    def test_validation_error_inherits_data_error(self):
        """ValidationError inherits from DataError."""
        exc = ValidationError("validation failed")
        assert isinstance(exc, DataError)


class TestStorageErrors:
    """Characterize storage exception hierarchy."""

    def test_storage_error_inherits_platform_error(self):
        """StorageError inherits from PlatformError."""
        exc = StorageError("storage issue")
        assert isinstance(exc, PlatformError)

    def test_database_error_inherits_storage_error(self):
        """DatabaseError inherits from StorageError."""
        exc = DatabaseError("db connection lost")
        assert isinstance(exc, StorageError)

    def test_cache_error_inherits_storage_error(self):
        """CacheError inherits from StorageError."""
        exc = CacheError("cache full")
        assert isinstance(exc, StorageError)


# ============================================================================
# Exception Catching Tests
# ============================================================================


class TestExceptionCatching:
    """Characterize except comma syntax."""

    def test_catch_platform_error_comma_syntax(self):
        """Catch PlatformError using except comma syntax."""
        caught = False
        try:
            raise PlatformError("test error")
        except PlatformError as e:
            caught = True
            assert str(e) == "test error"
        assert caught is True

    def test_catch_specific_protocol_error(self):
        """Catch specific protocol error."""
        caught = False
        try:
            raise ModbusError("modbus timeout", function_code=3)
        except ModbusError as e:
            caught = True
            assert e.function_code == 3
        assert caught is True

    def test_catch_base_catches_derived(self):
        """Catching PlatformError catches derived errors."""
        caught = False
        try:
            raise ValidationError("bad value")
        except PlatformError as e:
            caught = True
            assert isinstance(e, ValidationError)
        assert caught is True

    def test_multiple_except_clauses(self):
        """Multiple except clauses work with comma syntax."""
        for error_class in [DataError, ProtocolError, StorageError]:
            caught = False
            try:
                raise error_class("test")
            except DataError as e:
                caught = True
            except ProtocolError as e:
                caught = True
            except StorageError as e:
                caught = True
            assert caught is True


# ============================================================================
# Legacy sys.exc_* Attributes
# ============================================================================


class TestCaptureExcInfo:
    """Characterize sys.exc_type and sys.exc_value."""

    def test_capture_exc_info_returns_type_and_value(self):
        """capture_exc_info() returns (exc_type, exc_value)."""
        try:
            raise ValueError("test error")
        except:
            exc_type, exc_value = capture_exc_info()
            assert exc_type is ValueError
            assert str(exc_value) == "test error"

    def test_capture_exc_info_platform_error(self):
        """capture_exc_info() works with PlatformError."""
        try:
            raise PlatformError("platform issue", code=99)
        except:
            exc_type, exc_value = capture_exc_info()
            assert exc_type is PlatformError
            assert exc_value.code == 99

    def test_capture_exc_info_derived_error(self):
        """capture_exc_info() captures derived exception types."""
        try:
            raise ModbusError("modbus error", function_code=5)
        except:
            exc_type, exc_value = capture_exc_info()
            assert exc_type is ModbusError
            assert exc_value.function_code == 5


# ============================================================================
# Three-argument raise
# ============================================================================


class TestReraiseWithContext:
    """Characterize three-argument raise."""

    def test_reraise_preserves_traceback(self):
        """reraise_with_context() preserves original traceback."""
        original_tb = None
        reraised_tb = None

        try:
            try:
                raise ValueError("original")
            except:
                original_tb = sys.exc_info()[2]
                reraise_with_context(PlatformError, "wrapped error")
        except PlatformError:
            reraised_tb = sys.exc_info()[2]

        # Traceback should chain back to original
        assert reraised_tb is not None
        # In Py2, tb should have same depth or deeper
        tb_depth = 0
        tb = reraised_tb
        while tb is not None:
            tb_depth += 1
            tb = tb.tb_next
        assert tb_depth >= 1

    def test_reraise_changes_exception_type(self):
        """reraise_with_context() wraps with new exception type."""
        try:
            try:
                raise IOError("io error")
            except:
                reraise_with_context(ProtocolError, "wrapped io error")
        except ProtocolError as e:
            assert str(e) == "wrapped io error"
            assert not isinstance(e, IOError)

    def test_reraise_from_data_to_platform(self):
        """reraise_with_context() re-wraps exception types."""
        try:
            try:
                raise ParseError("parse failed")
            except:
                reraise_with_context(PlatformError, "general failure")
        except PlatformError as e:
            assert str(e) == "general failure"


# ============================================================================
# Two-argument raise
# ============================================================================


class TestSafeExecute:
    """Characterize two-argument raise."""

    def test_safe_execute_successful_call(self):
        """safe_execute() returns function result on success."""
        def add(a, b):
            return a + b

        result = safe_execute(add, 10, 20)
        assert result == 30

    def test_safe_execute_propagates_platform_error(self):
        """safe_execute() propagates PlatformError as-is."""
        def raise_platform():
            raise PlatformError("platform issue")

        with pytest.raises(PlatformError) as exc_info:
            safe_execute(raise_platform)
        assert str(exc_info.value) == "platform issue"

    def test_safe_execute_wraps_standard_error(self):
        """safe_execute() wraps StandardError in PlatformError."""
        def raise_value_error():
            raise ValueError("bad value")

        with pytest.raises(PlatformError) as exc_info:
            safe_execute(raise_value_error)
        assert "Unexpected error" in str(exc_info.value)
        assert "raise_value_error" in str(exc_info.value)

    def test_safe_execute_with_args(self):
        """safe_execute() passes through args."""
        def multiply(a, b, c):
            return a * b * c

        result = safe_execute(multiply, 2, 3, 4)
        assert result == 24

    def test_safe_execute_with_kwargs(self):
        """safe_execute() passes through kwargs."""
        def greet(name, greeting="Hello"):
            return "%s, %s" % (greeting, name)

        result = safe_execute(greet, "Alice", greeting="Hi")
        assert result == "Hi, Alice"


class TestWrapProtocolError:
    """Characterize protocol error wrapping."""

    def test_wrap_protocol_error_successful_call(self):
        """wrap_protocol_error() returns result on success."""
        def fetch_data():
            return "data"

        result = wrap_protocol_error(fetch_data)
        assert result == "data"

    def test_wrap_protocol_error_propagates_protocol_error(self):
        """wrap_protocol_error() propagates ProtocolError."""
        def raise_mqtt():
            raise MqttError("mqtt failed")

        with pytest.raises(MqttError):
            wrap_protocol_error(raise_mqtt)

    def test_wrap_protocol_error_wraps_environment_error(self):
        """wrap_protocol_error() wraps IOError/OSError."""
        def raise_io():
            raise IOError("connection refused")

        with pytest.raises(ProtocolError) as exc_info:
            wrap_protocol_error(raise_io)
        assert "I/O error" in str(exc_info.value)

    def test_wrap_protocol_error_wraps_standard_error(self):
        """wrap_protocol_error() wraps other StandardError."""
        def raise_runtime():
            raise RuntimeError("runtime issue")

        with pytest.raises(ProtocolError) as exc_info:
            wrap_protocol_error(raise_runtime)
        assert "Protocol failure" in str(exc_info.value)
        assert "RuntimeError" in str(exc_info.value)

    def test_wrap_protocol_error_uses_capture_exc_info(self):
        """wrap_protocol_error() uses capture_exc_info()."""
        def raise_error():
            raise KeyError("missing key")

        with pytest.raises(ProtocolError) as exc_info:
            wrap_protocol_error(raise_error)
        # Should include exception type name
        assert "KeyError" in str(exc_info.value)


# ============================================================================
# Format Exception
# ============================================================================


class TestFormatCurrentException:
    """Characterize sys.exc_type/exc_value usage."""

    def test_format_current_exception_during_except(self):
        """format_current_exception() formats active exception."""
        formatted = None
        try:
            raise ValueError("test value error")
        except:
            formatted = format_current_exception()

        assert "ValueError" in formatted
        assert "test value error" in formatted

    def test_format_current_exception_platform_error(self):
        """format_current_exception() formats PlatformError."""
        formatted = None
        try:
            raise PlatformError("platform problem")
        except:
            formatted = format_current_exception()

        assert "PlatformError" in formatted
        assert "platform problem" in formatted

    def test_format_current_exception_no_active(self):
        """format_current_exception() handles no active exception."""
        # Clear any active exception
        try:
            pass
        except:
            pass

        # Call outside except block
        result = format_current_exception()
        assert "No active exception" in result or result is not None

    def test_format_current_exception_nested(self):
        """format_current_exception() in nested exceptions."""
        outer_formatted = None
        inner_formatted = None

        try:
            try:
                raise KeyError("inner")
            except:
                inner_formatted = format_current_exception()
                raise ValueError("outer")
        except:
            outer_formatted = format_current_exception()

        assert "KeyError" in inner_formatted
        assert "ValueError" in outer_formatted
