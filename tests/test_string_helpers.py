# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/string_helpers.py

Captures current behavior including:
- unicode/str/basestring type checks
- StringIO/cStringIO usage
- Encoding detection and conversion
- Unicode normalization
- Mixed encoding handling
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from src.core.string_helpers import (
    detect_encoding,
    safe_decode,
    safe_encode,
    to_platform_string,
    normalise_sensor_label,
    safe_concat,
    build_csv_line,
    make_text_buffer,
    make_binary_buffer,
    validate_roundtrip,
)


class TestEncodingDetection:
    """Test encoding detection heuristics."""

    def test_detect_utf8(self):
        """Test detection of UTF-8 encoded bytes."""
        utf8_bytes = u"Hello 世界".encode("utf-8")
        encoding = detect_encoding(utf8_bytes)
        assert encoding == u"utf-8"

    def test_detect_latin1(self):
        """Test detection of Latin-1 encoded bytes."""
        # Latin-1 specific character
        latin1_bytes = u"café".encode("latin-1")
        encoding = detect_encoding(latin1_bytes)
        # Should detect as latin-1 or utf-8 (both valid for this string)
        assert encoding in (u"utf-8", u"latin-1")

    def test_detect_unicode_input_returns_utf8(self):
        """Test that unicode input returns utf-8."""
        encoding = detect_encoding(u"already unicode")
        assert encoding == u"utf-8"

    def test_fallback_to_latin1(self):
        """Test fallback to latin-1 for undecodable bytes."""
        # Invalid UTF-8 sequence
        bad_bytes = b"\xFF\xFE"
        encoding = detect_encoding(bad_bytes)
        assert encoding == u"latin-1"


class TestSafeDecode:
    """Test safe_decode() conversion."""

    def test_decode_bytes_to_unicode(self):
        """Test decoding byte string to unicode."""
        result = safe_decode(b"Hello", encoding=u"utf-8")
        assert isinstance(result, str)
        assert result == u"Hello"

    def test_decode_unicode_passthrough(self):
        """Test unicode input passes through unchanged."""
        input_str = u"Already unicode"
        result = safe_decode(input_str)
        assert result is input_str

    def test_decode_with_errors_replace(self):
        """Test error handling with replace strategy."""
        invalid_utf8 = b"\xFF\xFE invalid"
        result = safe_decode(invalid_utf8, errors=u"replace")
        assert isinstance(result, str)
        # Should contain replacement character
        assert u"\ufffd" in result or "?" in result

    def test_decode_basestring_handling(self):
        """Test that basestring (str or unicode) is handled."""
        str_input = "byte string"
        result = safe_decode(str_input)
        assert isinstance(result, str)


class TestSafeEncode:
    """Test safe_encode() conversion."""

    def test_encode_unicode_to_bytes(self):
        """Test encoding unicode to byte string."""
        result = safe_encode(u"Hello 世界", encoding=u"utf-8")
        assert isinstance(result, bytes)
        assert result == u"Hello 世界".encode("utf-8")

    def test_encode_bytes_passthrough(self):
        """Test byte string passes through unchanged."""
        byte_str = b"already bytes"
        result = safe_encode(byte_str)
        assert result == byte_str

    def test_encode_with_errors(self):
        """Test encoding with error handling."""
        # Character not in latin-1
        text = u"日本語"
        result = safe_encode(text, encoding=u"latin-1", errors=u"replace")
        assert isinstance(result, bytes)


class TestToPlatformString:
    """Test to_platform_string() conversion."""

    def test_unicode_to_platform_str(self):
        """Test converting unicode to platform str (bytes in Py2)."""
        result = to_platform_string(u"Hello")
        assert isinstance(result, str)
        assert result == "Hello"

    def test_bytes_passthrough(self):
        """Test byte string passes through."""
        result = to_platform_string("already str")
        assert result == "already str"


class TestNormaliseSensorLabel:
    """Test sensor label normalization."""

    def test_nfc_normalization(self):
        """Test NFC unicode normalization."""
        # Decomposed form
        decomposed = u"cafe\u0301"  # café with combining acute accent
        result = normalise_sensor_label(decomposed)

        # Should be in NFC form
        assert result == u"café"

    def test_strip_control_characters(self):
        """Test stripping C0/C1 control characters."""
        label_with_control = u"SENSOR\x00_\x01NAME"
        result = normalise_sensor_label(label_with_control)

        # Control characters should be removed
        assert "\x00" not in result
        assert "\x01" not in result
        assert result == u"SENSOR_NAME"

    def test_preserve_tab_and_newline(self):
        """Test that tab and newline are preserved."""
        label = u"SENSOR\tA\nB"
        result = normalise_sensor_label(label)

        # Tab and newline should remain (though strip() will remove trailing)
        assert "\t" in result

    def test_decode_byte_string_input(self):
        """Test normalizing byte string input."""
        byte_label = "SENSOR_NAME"
        result = normalise_sensor_label(byte_label)
        assert isinstance(result, str)


class TestSafeConcat:
    """Test safe string concatenation."""

    def test_concat_mixed_types(self):
        """Test concatenating mix of str and unicode."""
        result = safe_concat("byte", u"unicode", "string")
        assert isinstance(result, str)

    def test_concat_with_non_string(self):
        """Test concatenating non-string objects."""
        result = safe_concat(u"count: ", 42, u" items")
        assert isinstance(result, str)
        assert "count: 42 items" in result

    def test_concat_empty(self):
        """Test concatenating empty sequence."""
        result = safe_concat()
        assert result == u""


class TestBuildCsvLine:
    """Test CSV line building."""

    def test_simple_fields(self):
        """Test building CSV from simple fields."""
        result = build_csv_line([u"A", u"B", u"C"])
        assert result == u"A,B,C"

    def test_fields_with_separator(self):
        """Test escaping fields containing separator."""
        result = build_csv_line([u"A,B", u"C"])
        assert result == u'"A,B",C'

    def test_fields_with_quotes(self):
        """Test escaping fields containing quotes."""
        result = build_csv_line([u'Say "hello"', u"world"])
        assert result == u'"Say ""hello""",world'

    def test_fields_with_newline(self):
        """Test escaping fields containing newlines."""
        result = build_csv_line([u"Line1\nLine2", u"Field2"])
        assert u'"Line1\nLine2"' in result

    def test_mixed_types(self):
        """Test handling mixed field types."""
        result = build_csv_line([u"text", 123, 45.67])
        assert u"text,123,45.67" in result


class TestStringIOHelpers:
    """Test StringIO buffer creation."""

    def test_make_text_buffer(self):
        """Test creating text buffer."""
        buf = make_text_buffer(u"initial content")
        assert buf is not None

        content = buf.getvalue()
        # In Py2, StringIO stores str (bytes)
        assert isinstance(content, str)

    def test_make_binary_buffer(self):
        """Test creating binary buffer (cStringIO)."""
        buf = make_binary_buffer(b"binary\x00data")
        assert buf is not None

        content = buf.getvalue()
        assert content == b"binary\x00data"

    def test_empty_buffers(self):
        """Test creating empty buffers."""
        text_buf = make_text_buffer()
        binary_buf = make_binary_buffer()

        assert text_buf.getvalue() == b""
        assert binary_buf.getvalue() == b""


class TestValidateRoundtrip:
    """Test encoding round-trip validation."""

    def test_utf8_roundtrip_success(self):
        """Test successful UTF-8 round-trip."""
        text = u"Hello 世界 café"
        is_valid = validate_roundtrip(text, encoding=u"utf-8")
        assert is_valid is True

    def test_latin1_roundtrip_success(self):
        """Test successful Latin-1 round-trip."""
        text = u"café"
        is_valid = validate_roundtrip(text, encoding=u"latin-1")
        assert is_valid is True

    def test_roundtrip_failure(self):
        """Test round-trip failure with incompatible encoding."""
        text = u"日本語"  # Cannot be represented in Latin-1
        is_valid = validate_roundtrip(text, encoding=u"latin-1")
        assert is_valid is False

    def test_ascii_roundtrip(self):
        """Test ASCII round-trip."""
        text = u"ASCII only 123"
        is_valid = validate_roundtrip(text, encoding=u"ascii")
        assert is_valid is True


class TestEncodingEdgeCases:
    """Test edge cases in encoding handling."""

    def test_empty_string_decode(self):
        """Test decoding empty string."""
        result = safe_decode(b"")
        assert result == u""

    def test_empty_string_encode(self):
        """Test encoding empty string."""
        result = safe_encode(u"")
        assert result == b""

    def test_concat_unicode_literals(self):
        """Test concatenating u"" unicode literals."""
        result = safe_concat(u"Hello", u" ", u"World")
        assert result == u"Hello World"

    def test_build_csv_with_unicode_separator(self):
        """Test CSV building with unicode separator."""
        result = build_csv_line([u"A", u"B"], separator=u";")
        assert result == u"A;B"

    def test_normalise_japanese_label(self):
        """Test normalizing Japanese sensor labels."""
        label = u"温度センサー_001"
        result = normalise_sensor_label(label)
        assert isinstance(result, str)
        assert u"温度" in result
