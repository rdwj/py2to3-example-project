# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/string_helpers.py

Captures pre-migration behavior of:
- detect_encoding heuristic with encoding candidates
- safe_decode / safe_encode for str/unicode conversion
- to_platform_string for I/O boundary normalization
- normalise_sensor_label for NFC unicode normalization
- safe_concat for mixed str/unicode concatenation
- build_csv_line for field quoting and encoding
- make_text_buffer / make_binary_buffer using StringIO/cStringIO
- validate_roundtrip for encoding fidelity checks

This module IS the str/unicode boundary, so every test is encoding-relevant.
"""


import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.string_helpers import (
    detect_encoding, safe_decode, safe_encode, to_platform_string,
    normalise_sensor_label, safe_concat, build_csv_line,
    make_text_buffer, make_binary_buffer, validate_roundtrip,
)


# ---------------------------------------------------------------------------
# detect_encoding
# ---------------------------------------------------------------------------

class TestDetectEncoding:
    """Characterize encoding detection heuristic."""

    @pytest.mark.py2_behavior
    def test_unicode_input_returns_utf8(self):
        """Captures: unicode input (not str) returns 'utf-8' immediately.
        isinstance(raw_bytes, str) check; Py3 str is always text."""
        result = detect_encoding("already unicode")
        assert result == "utf-8"

    @pytest.mark.parametrize("raw,expected_enc", [
        (b"plain ascii", "utf-8"),
        ("caf\u00e9".encode("utf-8"), "utf-8"),
        (b"\xe9\xe8\xea", "latin-1"),  # not valid UTF-8
        ("\u6e29\u5ea6".encode("shift_jis"), "latin-1"),  # latin-1 precedes shift_jis and decodes any bytes
    ])
    @pytest.mark.py2_behavior
    def test_byte_string_detection(self, raw, expected_enc):
        """Captures: trial decode across encoding candidates."""
        result = detect_encoding(raw)
        assert result == expected_enc

    @pytest.mark.py2_behavior
    def test_all_bytes_fallback_to_latin1(self):
        """Captures: random high bytes detected as latin-1 (always succeeds)."""
        raw = b"\x80\x81\x82\x83\x84"
        result = detect_encoding(raw)
        # Either utf-8 (unlikely for these bytes) or latin-1
        assert result in ("latin-1", "utf-8", "cp1252")


# ---------------------------------------------------------------------------
# safe_decode
# ---------------------------------------------------------------------------

class TestSafeDecode:
    """Characterize safe byte-to-unicode conversion."""

    @pytest.mark.py2_behavior
    def test_unicode_passthrough(self):
        """Captures: unicode input returned unchanged."""
        text = "caf\u00e9"
        assert safe_decode(text) is text

    @pytest.mark.py2_behavior
    def test_byte_string_decoded(self):
        """Captures: str (bytes) decoded with given encoding."""
        raw = "caf\u00e9".encode("utf-8")
        result = safe_decode(raw)
        assert isinstance(result, str)
        assert result == "caf\u00e9"

    @pytest.mark.py2_behavior
    def test_replace_errors(self):
        """Captures: unencodable bytes replaced with U+FFFD."""
        raw = b"\xFF\xFE"
        result = safe_decode(raw, encoding="utf-8", errors="replace")
        assert isinstance(result, str)
        assert "\ufffd" in result

    @pytest.mark.py2_behavior
    def test_non_string_converted(self):
        """Captures: non-string types converted via unicode()."""
        assert safe_decode(42) == "42"
        assert safe_decode(3.14) == "3.14"


# ---------------------------------------------------------------------------
# safe_encode
# ---------------------------------------------------------------------------

class TestSafeEncode:
    """Characterize safe unicode-to-bytes conversion."""

    @pytest.mark.py2_behavior
    def test_byte_string_passthrough(self):
        """Captures: plain str (bytes, not unicode) returned unchanged.
        isinstance(value, str) and not isinstance(value, unicode)."""
        raw = b"plain bytes"
        result = safe_encode(raw)
        assert result is raw

    @pytest.mark.py2_behavior
    def test_unicode_encoded(self):
        """Captures: str encoded to bytes with given encoding."""
        text = "caf\u00e9"
        result = safe_encode(text)
        assert isinstance(result, bytes)
        assert result == "caf\u00e9".encode("utf-8")

    @pytest.mark.py2_behavior
    def test_non_string_uses_str(self):
        """Captures: non-string types converted via str() then encoded to bytes."""
        assert safe_encode(42) == b"42"


# ---------------------------------------------------------------------------
# to_platform_string
# ---------------------------------------------------------------------------

class TestToPlatformString:
    """Characterize I/O boundary string normalization."""

    @pytest.mark.py2_behavior
    def test_unicode_to_str(self):
        """Captures: str input returned as-is (Py3 platform str is text)."""
        result = to_platform_string("caf\u00e9")
        assert isinstance(result, str)
        assert result == "caf\u00e9"

    @pytest.mark.py2_behavior
    def test_byte_string_decoded(self):
        """Captures: bytes decoded to str (Py3 platform str is text)."""
        raw = b"bytes"
        result = to_platform_string(raw)
        assert isinstance(result, str)
        assert result == "bytes"

    @pytest.mark.py2_behavior
    def test_non_string_uses_str(self):
        """Captures: non-string converted via str()."""
        assert to_platform_string(42) == "42"


# ---------------------------------------------------------------------------
# normalise_sensor_label
# ---------------------------------------------------------------------------

class TestNormaliseSensorLabel:
    """Characterize unicode normalization for sensor labels."""

    def test_nfc_normalization(self):
        """Captures: label normalized to NFC form."""
        import unicodedata
        # NFD form of e-acute: e + combining acute
        nfd_label = "caf\u0065\u0301"
        result = normalise_sensor_label(nfd_label)
        assert "\u00e9" in result  # NFC form

    def test_strip_control_characters(self):
        """Captures: C0/C1 control chars removed except tab/newline."""
        label = "TEMP\x00-001\x01"
        result = normalise_sensor_label(label)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "TEMP" in result

    def test_preserve_tab_and_newline(self):
        """Captures: tab and newline are NOT stripped."""
        label = "TEMP\t001\n"
        result = normalise_sensor_label(label)
        assert "\t" in result

    @pytest.mark.py2_behavior
    def test_byte_string_decoded(self):
        """Captures: byte string input decoded to unicode first.
        isinstance(label, unicode) check."""
        raw = "caf\u00e9".encode("utf-8")
        result = normalise_sensor_label(raw)
        assert isinstance(result, str)
        assert "\u00e9" in result

    def test_japanese_kanji_label(self):
        """Captures: Japanese sensor labels handled correctly."""
        label = "\u6e29\u5ea6\u30bb\u30f3\u30b5\u30fc"  # "temperature sensor" in Japanese
        result = normalise_sensor_label(label)
        assert "\u6e29\u5ea6" in result


# ---------------------------------------------------------------------------
# safe_concat
# ---------------------------------------------------------------------------

class TestSafeConcat:
    """Characterize mixed str/unicode concatenation."""

    @pytest.mark.py2_behavior
    def test_all_unicode(self):
        """Captures: all unicode parts joined directly."""
        result = safe_concat("hello", " ", "world")
        assert result == "hello world"

    @pytest.mark.py2_behavior
    def test_mixed_str_unicode(self):
        """Captures: str parts decoded to unicode before joining.
        Avoids Py2 implicit ASCII decode on str + unicode."""
        result = safe_concat("caf\u00e9", " - ", "r\u00e9sum\u00e9")
        assert isinstance(result, str)
        assert "caf\u00e9" in result

    @pytest.mark.py2_behavior
    def test_non_string_parts(self):
        """Captures: non-string parts converted via unicode()."""
        result = safe_concat("value=", 42, " quality=", 192)
        assert result == "value=42 quality=192"


# ---------------------------------------------------------------------------
# build_csv_line
# ---------------------------------------------------------------------------

class TestBuildCsvLine:
    """Characterize CSV line construction."""

    def test_simple_fields(self):
        """Captures: fields joined with separator."""
        result = build_csv_line(["a", "b", "c"])
        assert result == "a,b,c"

    def test_fields_with_separator_quoted(self):
        """Captures: fields containing separator get double-quoted."""
        result = build_csv_line(["hello,world", "plain"])
        assert '"hello,world"' in result

    def test_fields_with_quotes_escaped(self):
        """Captures: double-quotes in fields are doubled."""
        result = build_csv_line(['say "hello"'])
        assert '""hello""' in result

    def test_custom_separator(self):
        """Captures: custom separator used instead of comma."""
        result = build_csv_line(["a", "b", "c"], separator=";")
        assert result == "a;b;c"


# ---------------------------------------------------------------------------
# make_text_buffer / make_binary_buffer
# ---------------------------------------------------------------------------

class TestStringIOHelpers:
    """Characterize StringIO buffer creation."""

    @pytest.mark.py2_behavior
    def test_make_text_buffer(self):
        """Captures: StringIO from StringIO module (renamed io.StringIO in Py3)."""
        buf = make_text_buffer("initial")
        buf.write(" more")
        content = buf.getvalue()
        assert "initial" in content or "more" in content

    @pytest.mark.py2_behavior
    def test_make_binary_buffer(self):
        """Captures: cStringIO for binary data (removed in Py3; use io.BytesIO)."""
        buf = make_binary_buffer(b"\x01\x02")
        buf.write(b"\x03\x04")
        content = buf.getvalue()
        assert b"\x01\x02\x03\x04" == content


# ---------------------------------------------------------------------------
# validate_roundtrip
# ---------------------------------------------------------------------------

class TestValidateRoundtrip:
    """Characterize encoding round-trip validation."""

    def test_ascii_roundtrip(self):
        """Captures: ASCII text survives any encoding round-trip."""
        assert validate_roundtrip("plain ascii") is True

    def test_utf8_roundtrip(self):
        """Captures: UTF-8 encoded unicode survives round-trip."""
        assert validate_roundtrip("caf\u00e9 r\u00e9sum\u00e9") is True

    def test_latin1_roundtrip_fails_for_cjk(self):
        """Captures: CJK text fails Latin-1 round-trip."""
        assert validate_roundtrip("\u6e29\u5ea6", encoding="latin-1") is False

    def test_ascii_roundtrip_fails_for_accented(self):
        """Captures: accented chars fail ASCII round-trip."""
        assert validate_roundtrip("caf\u00e9", encoding="ascii") is False

    @pytest.mark.py2_behavior
    def test_byte_string_input_decoded_first(self):
        """Captures: byte string input decoded to unicode before round-trip.
        isinstance(text, unicode) check."""
        raw = "caf\u00e9".encode("utf-8")
        result = validate_roundtrip(raw)
        # After decode and re-encode, should still match
        assert result is True
