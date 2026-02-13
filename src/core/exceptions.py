# -*- coding: utf-8 -*-
"""
Exception hierarchy for the Legacy Industrial Data Platform.

All platform-specific exceptions descend from ``PlatformError`` which
itself inherits from ``StandardError`` (renamed to ``Exception`` in
Python 3).  The hierarchy allows callers to catch broad categories
(e.g. all protocol errors) or specific conditions (e.g. a MODBUS
timeout).
"""

import sys


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------

class PlatformError(StandardError):
    """Root of the platform exception hierarchy."""

    def __init__(self, message=None, code=None):
        StandardError.__init__(self, message)
        self.code = code


# ---------------------------------------------------------------------------
# Protocol layer
# ---------------------------------------------------------------------------

class ProtocolError(PlatformError):
    """Raised when a communication protocol encounters an error."""
    pass


class ModbusError(ProtocolError):
    """MODBUS-specific protocol errors (timeouts, CRC failures, etc.)."""

    def __init__(self, message, function_code=None, exception_code=None):
        ProtocolError.__init__(self, message, code=exception_code)
        self.function_code = function_code
        self.exception_code = exception_code


class SerialError(ProtocolError):
    """RS-232/RS-485 serial communication errors."""
    pass


class MqttError(ProtocolError):
    """MQTT broker communication errors."""
    pass


class OpcUaError(ProtocolError):
    """OPC-UA client errors (bad node IDs, access denied, etc.)."""
    pass


# ---------------------------------------------------------------------------
# Data processing layer
# ---------------------------------------------------------------------------

class DataError(PlatformError):
    """Raised when incoming data fails validation or parsing."""
    pass


class EncodingError(DataError):
    """Character encoding problems -- very common in our mixed-encoding
    environment."""
    pass


class ParseError(DataError):
    """Structural parse failure (corrupt packets, truncated records)."""
    pass


class ValidationError(DataError):
    """Semantic validation failure (out-of-range values, missing
    required fields)."""
    pass


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------

class StorageError(PlatformError):
    """Raised when a storage backend fails."""
    pass


class DatabaseError(StorageError):
    """Database connection or query errors."""
    pass


class CacheError(StorageError):
    """Cache read/write errors."""
    pass


# ---------------------------------------------------------------------------
# Error-handling utilities
# ---------------------------------------------------------------------------

def capture_exc_info():
    """Capture the current exception using the legacy ``sys.exc_type``
    and ``sys.exc_value`` attributes.

    In Python 3 these were removed; ``sys.exc_info()`` is the
    replacement.
    """
    return sys.exc_type, sys.exc_value


def reraise_with_context(new_exc_class, message):
    """Re-raise the current exception wrapped in *new_exc_class*,
    preserving the original traceback.

    Uses the three-argument ``raise`` form:
        raise ExcClass, value, traceback

    In Python 3 this becomes ``raise ExcClass(value).with_traceback(tb)``
    or implicit chaining via ``raise ... from ...``.
    """
    tb = sys.exc_info()[2]
    raise new_exc_class, message, tb


def safe_execute(func, *args, **kwargs):
    """Call *func* and translate any exception into a ``PlatformError``.

    Uses the comma-style ``except`` syntax and two-argument ``raise``.
    """
    try:
        return func(*args, **kwargs)
    except PlatformError, e:
        # Already a platform error -- propagate as-is
        raise
    except StandardError, e:
        raise PlatformError, "Unexpected error in %s: %s" % (func.__name__, e)


def wrap_protocol_error(func, *args, **kwargs):
    """Call a protocol-layer function, wrapping low-level exceptions
    in ``ProtocolError``."""
    try:
        return func(*args, **kwargs)
    except ProtocolError, e:
        raise
    except EnvironmentError, e:
        # Socket errors, OS errors from serial ports, etc.
        raise ProtocolError, "I/O error: %s" % e
    except StandardError, e:
        exc_type, exc_value = capture_exc_info()
        raise ProtocolError, "Protocol failure (%s): %s" % (exc_type.__name__, exc_value)


def format_current_exception():
    """Format the current exception for logging using legacy sys
    attributes."""
    exc_type = sys.exc_type
    exc_value = sys.exc_value
    if exc_type is None:
        return "No active exception"
    return "%s: %s" % (exc_type.__name__, exc_value)
