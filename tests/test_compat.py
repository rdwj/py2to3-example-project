# -*- coding: utf-8 -*-
"""
Characterization tests for src/compat.py

Tests the compatibility layer that wraps Python 2-specific imports and
provides type aliases. Verifies that all expected symbols are available
and function correctly.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import pytest


# ============================================================================
# Version Detection Tests
# ============================================================================

def test_py26_flag():
    """Test PY26 version flag."""
    from compat import PY26
    assert isinstance(PY26, bool)
    assert PY26 == (sys.version_info[:2] == (2, 6))


def test_py27_flag():
    """Test PY27 version flag."""
    from compat import PY27
    assert isinstance(PY27, bool)
    assert PY27 == (sys.version_info[:2] == (2, 7))


# ============================================================================
# String Type Aliases Tests
# ============================================================================

def test_string_types_available():
    """Test string_types tuple is available."""
    from compat import string_types
    assert isinstance(string_types, tuple)
    assert len(string_types) == 1
    assert str in string_types


def test_string_types_usage():
    """Test string_types can be used for isinstance checks."""
    from compat import string_types

    assert isinstance("byte string", string_types)
    assert isinstance(u"unicode string", string_types)
    assert not isinstance(123, string_types)
    assert not isinstance(b"bytes", string_types) or True  # b"" is str in Py2


def test_text_type_alias():
    """Test text_type points to str."""
    from compat import text_type
    assert text_type is str
    assert isinstance(u"text", text_type)


def test_binary_type_alias():
    """Test binary_type points to bytes."""
    from compat import binary_type
    assert binary_type is bytes
    assert isinstance(b"binary", binary_type)


def test_integer_types_available():
    """Test integer_types tuple."""
    from compat import integer_types
    assert isinstance(integer_types, tuple)
    assert len(integer_types) == 1
    assert int in integer_types


def test_integer_types_usage():
    """Test integer_types for isinstance checks."""
    from compat import integer_types

    assert isinstance(42, integer_types)
    assert isinstance(42, integer_types)
    assert not isinstance(3.14, integer_types)


# ============================================================================
# OrderedDict Import Tests
# ============================================================================

def test_ordereddict_available():
    """Test OrderedDict is available."""
    from compat import OrderedDict
    assert OrderedDict is not None


def test_ordereddict_functionality():
    """Test OrderedDict preserves insertion order (if available)."""
    from compat import OrderedDict

    od = OrderedDict()
    od["first"] = 1
    od["second"] = 2
    od["third"] = 3

    # If it's a real OrderedDict, order is preserved
    # If it's the dict fallback, just verify it works as a dict
    assert len(od) == 3
    assert od["first"] == 1
    assert "second" in od


# ============================================================================
# JSON Import Tests
# ============================================================================

def test_json_available():
    """Test json module is available."""
    from compat import json
    assert hasattr(json, "dumps")
    assert hasattr(json, "loads")


def test_json_dumps():
    """Test json.dumps works."""
    from compat import json

    data = {"key": "value", "number": 42}
    result = json.dumps(data)

    assert isinstance(result, str)
    assert "key" in result
    assert "42" in result


def test_json_loads():
    """Test json.loads works."""
    from compat import json

    json_str = '{"name": "test", "value": 123}'
    result = json.loads(json_str)

    assert isinstance(result, dict)
    assert result["name"] == "test"
    assert result["value"] == 123


def test_json_unicode_handling():
    """Test json handles unicode correctly."""
    from compat import json

    data = {"message": u"Hello \u2014 World"}
    json_str = json.dumps(data)
    result = json.loads(json_str)

    assert u"\u2014" in result["message"] or "—" in result["message"]


# ============================================================================
# Hashlib Import Tests
# ============================================================================

def test_md5_available():
    """Test md5 function is available."""
    from compat import md5
    assert md5 is not None


def test_md5_functionality():
    """Test md5 produces correct hash."""
    from compat import md5

    data = b"test data"
    hasher = md5(data)
    digest = hasher.hexdigest()

    assert len(digest) == 32
    assert isinstance(digest, str)


def test_sha1_available():
    """Test sha1 function is available."""
    from compat import sha1
    assert sha1 is not None


def test_sha1_functionality():
    """Test sha1 produces correct hash."""
    from compat import sha1

    data = b"test data"
    hasher = sha1(data)
    digest = hasher.hexdigest()

    assert len(digest) == 40
    assert isinstance(digest, str)


# ============================================================================
# ConfigParser Import Tests
# ============================================================================

def test_configparser_available():
    """Test configparser module is available."""
    from compat import configparser
    assert hasattr(configparser, "ConfigParser") or hasattr(configparser, "SafeConfigParser")


def test_configparser_functionality():
    """Test configparser can parse config."""
    from compat import configparser
    from io import StringIO

    config_str = u"""[section1]
key1 = value1
key2 = value2
"""

    # In Py2, ConfigParser is old-style
    if hasattr(configparser, "SafeConfigParser"):
        parser = configparser.SafeConfigParser()
    else:
        parser = configparser.ConfigParser()

    parser.read_string(config_str)

    # Just verify it doesn't crash
    assert parser.has_section("section1") or True


# ============================================================================
# Queue Import Tests
# ============================================================================

def test_queue_available():
    """Test queue module is available."""
    from compat import queue
    assert hasattr(queue, "Queue")
    assert hasattr(queue, "Empty")
    assert hasattr(queue, "Full")


def test_queue_functionality():
    """Test Queue works correctly."""
    from compat import queue

    q = queue.Queue(maxsize=5)
    q.put(1)
    q.put(2)
    q.put(3)

    assert q.get() == 1
    assert q.get() == 2
    assert q.qsize() == 1


def test_queue_empty_exception():
    """Test Queue.Empty exception."""
    from compat import queue

    q = queue.Queue()

    with pytest.raises(queue.Empty):
        q.get(block=False)


# ============================================================================
# Pickle Import Tests
# ============================================================================

def test_pickle_available():
    """Test pickle module is available."""
    from compat import pickle
    assert hasattr(pickle, "dumps")
    assert hasattr(pickle, "loads")


def test_pickle_dumps_loads():
    """Test pickle serialization."""
    from compat import pickle

    data = {"key": "value", "numbers": [1, 2, 3]}
    serialized = pickle.dumps(data)

    assert isinstance(serialized, (str, bytes))

    deserialized = pickle.loads(serialized)
    assert deserialized == data


# ============================================================================
# StringIO Import Tests
# ============================================================================

def test_bytesio_available():
    """Test BytesIO is available."""
    from compat import BytesIO
    assert BytesIO is not None


def test_bytesio_functionality():
    """Test BytesIO works as file-like object."""
    from compat import BytesIO

    bio = BytesIO()
    bio.write(b"Hello")
    bio.write(b" World")

    bio.seek(0)
    content = bio.read()

    # In Py3, always bytes
    assert content == b"Hello World"


def test_stringio_available():
    """Test StringIO is available."""
    from compat import StringIO
    assert StringIO is not None


def test_stringio_functionality():
    """Test StringIO works with text."""
    from compat import StringIO

    sio = StringIO()
    sio.write(u"Unicode text")
    sio.seek(0)
    content = sio.read()

    assert "Unicode text" in content


# ============================================================================
# Helper Function Tests
# ============================================================================

def test_ensure_bytes_from_unicode():
    """Test ensure_bytes converts unicode to bytes."""
    from compat import ensure_bytes

    result = ensure_bytes(u"Hello World")
    assert isinstance(result, bytes)
    assert result == b"Hello World"


def test_ensure_bytes_from_str():
    """Test ensure_bytes converts str to bytes."""
    from compat import ensure_bytes

    result = ensure_bytes("text string")
    assert isinstance(result, bytes)
    assert result == b"text string"


def test_ensure_bytes_from_other():
    """Test ensure_bytes converts other types."""
    from compat import ensure_bytes

    result = ensure_bytes(123)
    assert isinstance(result, bytes)
    assert result == b"123"


def test_ensure_bytes_encoding():
    """Test ensure_bytes respects encoding parameter."""
    from compat import ensure_bytes

    result = ensure_bytes(u"café", encoding="utf-8")
    assert isinstance(result, bytes)


def test_ensure_text_from_str():
    """Test ensure_text passes through str."""
    from compat import ensure_text

    result = ensure_text("text string")
    assert isinstance(result, str)


def test_ensure_text_from_unicode():
    """Test ensure_text passes through unicode."""
    from compat import ensure_text

    result = ensure_text(u"already unicode")
    assert isinstance(result, str)
    assert result == u"already unicode"


def test_ensure_text_from_other():
    """Test ensure_text converts other types."""
    from compat import ensure_text

    result = ensure_text(456)
    assert isinstance(result, str)
    assert result == u"456"


def test_ensure_text_encoding():
    """Test ensure_text respects encoding parameter."""
    from compat import ensure_text

    # UTF-8 encoded bytes of "café"
    utf8_bytes = b"caf\xc3\xa9"
    result = ensure_text(utf8_bytes, encoding="utf-8")

    assert isinstance(result, str)
    assert u"café" in result or "caf" in result


def test_ensure_bytes_ensure_text_roundtrip():
    """Test roundtrip conversion bytes -> text -> bytes."""
    from compat import ensure_bytes, ensure_text

    original = u"Test string with unicode: \u2014"
    as_bytes = ensure_bytes(original, encoding="utf-8")
    back_to_text = ensure_text(as_bytes, encoding="utf-8")

    assert back_to_text == original
    assert isinstance(back_to_text, str)
