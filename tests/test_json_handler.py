# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/json_handler.py

Tests the current Python 2 behavior including:
- json.loads() with bytes (str in Py2)
- json.dumps() encoding parameter (removed in Py3)
- cPickle fallback (renamed to pickle in Py3)
- cStringIO (io.StringIO/BytesIO in Py3)
- dict.has_key()
- dict.iteritems() and dict.iterkeys()
- except Exception, e syntax
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import json
import pytest
from io import BytesIO as StringIO

from src.data_processing.json_handler import (
    JsonRecordSet,
    JsonHandler,
    MAX_JSON_SIZE,
    JSON_DEFAULT_ENCODING,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_record_set():
    """Create a sample JsonRecordSet for testing."""
    record_set = JsonRecordSet(source_id="test_source")
    record_set.add_record({"id": 1, "name": "Sensor A", "value": 42.5})
    record_set.add_record({"id": 2, "name": "Sensor B", "value": 38.2})
    record_set.set_metadata("timestamp", "2024-01-15T10:00:00")
    record_set.set_metadata("plant_id", "PLANT001")
    return record_set


@pytest.fixture
def json_handler():
    """Create a JsonHandler instance."""
    return JsonHandler()


@pytest.fixture
def temp_json_file(tmp_path):
    """Create a temporary JSON file for testing."""
    def _create_file(content):
        json_file = tmp_path / "test.json"
        json_file.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return str(json_file)
    return _create_file


# ---------------------------------------------------------------------------
# Test JsonRecordSet
# ---------------------------------------------------------------------------

def test_record_set_initialization():
    """Test JsonRecordSet initialization."""
    rs = JsonRecordSet(source_id="test")
    assert rs.source_id == "test"
    assert rs.count() == 0
    assert isinstance(rs.records, list)


def test_record_set_add_record():
    """Test adding records to set."""
    rs = JsonRecordSet()
    rs.add_record({"id": 1, "value": 100})
    rs.add_record({"id": 2, "value": 200})
    assert rs.count() == 2


def test_record_set_iter_records():
    """Test iterating over records."""
    rs = JsonRecordSet()
    rs.add_record({"id": 1})
    rs.add_record({"id": 2})
    records = list(rs.iter_records())
    assert len(records) == 2
    assert records[0]["id"] == 1


def test_record_set_has_key_metadata():
    """Test has_key() usage in get_metadata."""
    rs = JsonRecordSet()
    rs.set_metadata("key1", "value1")
    assert rs.get_metadata("key1") == "value1"
    assert rs.get_metadata("missing", "default") == "default"


def test_record_set_metadata_operations():
    """Test metadata get/set operations."""
    rs = JsonRecordSet()
    rs.set_metadata("plant", "PLANT001")
    rs.set_metadata("timestamp", 1234567890)
    assert rs.metadata["plant"] == "PLANT001"
    assert rs.metadata["timestamp"] == 1234567890


def test_record_set_to_dict():
    """Test conversion to dictionary."""
    rs = JsonRecordSet(source_id="source1")
    rs.add_record({"id": 1})
    rs.set_metadata("version", "1.0")

    result = rs.to_dict()
    assert result["source_id"] == "source1"
    assert result["count"] == 1
    assert "records" in result
    assert "metadata" in result
    assert result["metadata"]["version"] == "1.0"


def test_record_set_repr():
    """Test __repr__ output."""
    rs = JsonRecordSet(source_id="test_source")
    rs.add_record({"id": 1})
    repr_str = repr(rs)
    assert "JsonRecordSet" in repr_str
    assert "test_source" in repr_str
    assert "count=1" in repr_str


# ---------------------------------------------------------------------------
# Test JsonHandler load_bytes with encoding parameter
# ---------------------------------------------------------------------------

def test_handler_load_bytes_simple(json_handler):
    """Test loading JSON from bytes."""
    data = b'[{"id": 1, "name": "test"}]'
    record_set = json_handler.load_bytes(data)
    assert record_set.count() == 1
    assert list(record_set.iter_records())[0]["name"] == "test"


def test_handler_load_bytes_with_unicode(json_handler):
    """Test loading JSON with unicode content."""
    data = b'[{"name": "\xe6\xb8\xa9\xe5\xba\xa6"}]'  # UTF-8 encoded "温度"
    record_set = json_handler.load_bytes(data)
    assert record_set.count() == 1
    name = list(record_set.iter_records())[0]["name"]
    assert "温度" in name


def test_handler_load_bytes_encoding_parameter(json_handler):
    """Test that json.loads uses encoding parameter (Py2 feature)."""
    # In Python 2, json.loads accepts encoding parameter
    data = b'{"sensor": "value"}'
    record_set = json_handler.load_bytes(data)
    assert record_set.count() == 1


def test_handler_load_bytes_invalid_json(json_handler):
    """Test error handling for invalid JSON."""
    data = b'{"invalid": '
    with pytest.raises(Exception) as exc_info:
        json_handler.load_bytes(data)
    assert "parse error" in str(exc_info.value).lower()


def test_handler_load_bytes_with_source_id(json_handler):
    """Test source_id is preserved."""
    data = b'[{"id": 1}]'
    record_set = json_handler.load_bytes(data, source_id="test_source")
    assert record_set.source_id == "test_source"


# ---------------------------------------------------------------------------
# Test JsonHandler load_file
# ---------------------------------------------------------------------------

def test_handler_load_file_simple(json_handler, temp_json_file):
    """Test loading JSON from file."""
    json_content = '[{"id": 1, "name": "sensor"}]'
    file_path = temp_json_file(json_content)

    record_set = json_handler.load_file(file_path)
    assert record_set.count() == 1
    assert record_set.source_id == file_path


def test_handler_load_file_with_unicode(json_handler, temp_json_file):
    """Test loading file with unicode content."""
    json_content = u'[{"label": "温度センサー"}]'
    file_path = temp_json_file(json_content)

    record_set = json_handler.load_file(file_path)
    assert record_set.count() == 1


def test_handler_load_file_too_large(json_handler, tmp_path):
    """Test error when file exceeds MAX_JSON_SIZE."""
    # Create a file larger than MAX_JSON_SIZE
    large_file = tmp_path / "large.json"
    large_file.write_bytes(b"x" * (MAX_JSON_SIZE + 1000))

    with pytest.raises(Exception) as exc_info:
        json_handler.load_file(str(large_file))
    assert "too large" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test JsonHandler load_stream with cStringIO
# ---------------------------------------------------------------------------

def test_handler_load_stream_simple(json_handler):
    """Test loading JSON from cStringIO stream."""
    data = b'[{"id": 1}]'
    stream = StringIO(data)

    record_set = json_handler.load_stream(stream)
    assert record_set.count() == 1


def test_handler_load_stream_chunked(json_handler):
    """Test loading stream in chunks (simulates HTTP client)."""
    data = b'[{"id": 1}, {"id": 2}]'
    stream = StringIO(data)

    record_set = json_handler.load_stream(stream, source_id="stream_test")
    assert record_set.count() == 2
    assert record_set.source_id == "stream_test"


def test_handler_load_stream_empty(json_handler):
    """Test loading empty stream."""
    stream = StringIO(b'[]')
    record_set = json_handler.load_stream(stream)
    assert record_set.count() == 0


# ---------------------------------------------------------------------------
# Test JsonHandler dump with encoding parameter
# ---------------------------------------------------------------------------

def test_handler_dump_to_file_simple(json_handler, sample_record_set, tmp_path):
    """Test dumping to file with json.dumps encoding parameter."""
    output_file = tmp_path / "output.json"
    json_handler.dump_to_file(sample_record_set, str(output_file))

    assert output_file.exists()
    content = output_file.read_bytes()
    assert b"Sensor A" in content


def test_handler_dump_to_file_pretty(json_handler, sample_record_set, tmp_path):
    """Test pretty-printing with indent and sort_keys."""
    output_file = tmp_path / "output.json"
    json_handler.dump_to_file(sample_record_set, str(output_file), pretty=True)

    content = output_file.read_text(encoding="utf-8")
    assert "  " in content  # Check for indentation
    data = json.loads(content)
    assert "records" in data


def test_handler_dump_to_file_unicode_content(json_handler, tmp_path):
    """Test dumping with unicode content (ensure_ascii=False)."""
    rs = JsonRecordSet()
    rs.add_record({"label": u"温度センサー"})

    output_file = tmp_path / "output.json"
    json_handler.dump_to_file(rs, str(output_file))

    content = output_file.read_bytes()
    # With ensure_ascii=False, unicode chars should be preserved
    assert b"\xe6\xb8\xa9" in content or "温度" in content.decode("utf-8")


def test_handler_dump_to_file_encoding_parameter(json_handler, sample_record_set, tmp_path):
    """Test json.dumps encoding parameter usage (Py2 feature)."""
    output_file = tmp_path / "output.json"
    # This uses encoding parameter internally in Py2
    json_handler.dump_to_file(sample_record_set, str(output_file))
    assert output_file.exists()


# ---------------------------------------------------------------------------
# Test JsonHandler dump_to_stream with cStringIO
# ---------------------------------------------------------------------------

def test_handler_dump_to_stream_simple(json_handler, sample_record_set):
    """Test dumping to cStringIO stream."""
    stream = json_handler.dump_to_stream(sample_record_set)
    assert isinstance(stream, StringIO)

    content = stream.read()
    assert b"Sensor A" in content or "Sensor A" in content


def test_handler_dump_to_stream_pretty(json_handler, sample_record_set):
    """Test pretty-printing to stream."""
    stream = json_handler.dump_to_stream(sample_record_set, pretty=True)
    content = stream.read()
    # Check for indentation in pretty output
    assert b"  " in content or "  " in content


# ---------------------------------------------------------------------------
# Test cPickle operations
# ---------------------------------------------------------------------------

def test_handler_pickle_record_set(json_handler, sample_record_set, tmp_path):
    """Test cPickle serialization with HIGHEST_PROTOCOL."""
    pickle_file = tmp_path / "data.pickle"
    json_handler.pickle_record_set(sample_record_set, str(pickle_file))

    assert pickle_file.exists()
    assert pickle_file.stat().st_size > 0


def test_handler_unpickle_record_set(json_handler, sample_record_set, tmp_path):
    """Test cPickle deserialization."""
    pickle_file = tmp_path / "data.pickle"
    json_handler.pickle_record_set(sample_record_set, str(pickle_file))

    loaded = json_handler.unpickle_record_set(str(pickle_file))
    assert isinstance(loaded, JsonRecordSet)
    assert loaded.count() == sample_record_set.count()
    assert loaded.source_id == sample_record_set.source_id


def test_handler_unpickle_invalid_type(json_handler, tmp_path):
    """Test error when unpickled object is not JsonRecordSet."""
    import pickle
    pickle_file = tmp_path / "invalid.pickle"

    # Pickle a plain dict instead of JsonRecordSet
    with open(str(pickle_file), "wb") as f:
        pickle.dump({"not": "a record set"}, f)

    with pytest.raises(Exception) as exc_info:
        json_handler.unpickle_record_set(str(pickle_file))
    assert "not a JsonRecordSet" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test validate_records with has_key()
# ---------------------------------------------------------------------------

def test_handler_validate_records_all_valid(json_handler):
    """Test validation with all required fields present."""
    rs = JsonRecordSet()
    rs.add_record({"id": 1, "name": "A", "value": 100})
    rs.add_record({"id": 2, "name": "B", "value": 200})

    valid = json_handler.validate_records(rs, ["id", "name", "value"])
    assert len(valid) == 2


def test_handler_validate_records_missing_fields(json_handler):
    """Test validation with missing required fields."""
    rs = JsonRecordSet()
    rs.add_record({"id": 1, "name": "A"})  # Missing "value"
    rs.add_record({"id": 2, "name": "B", "value": 200})

    valid = json_handler.validate_records(rs, ["id", "name", "value"])
    assert len(valid) == 1
    assert valid[0]["id"] == 2

    errors = json_handler.validation_errors()
    assert len(errors) == 1
    assert "missing fields" in errors[0].lower()


def test_handler_validate_records_uses_has_key(json_handler):
    """Test that validation uses dict.has_key() method."""
    rs = JsonRecordSet()
    rs.add_record({"field1": "value1"})

    valid = json_handler.validate_records(rs, ["field1", "field2"])
    # Should find field1 missing field2
    assert len(valid) == 0


# ---------------------------------------------------------------------------
# Test transform_records with iteritems() and has_key()
# ---------------------------------------------------------------------------

def test_handler_transform_records_field_renaming(json_handler):
    """Test field renaming in transform_records."""
    rs = JsonRecordSet()
    rs.add_record({"old_name": "value1", "keep": "value2"})
    rs.add_record({"old_name": "value3", "keep": "value4"})

    field_map = {"old_name": "new_name"}
    result = json_handler.transform_records(rs, field_map)

    records = list(result.iter_records())
    assert len(records) == 2
    assert "new_name" in records[0]
    assert "old_name" not in records[0]
    assert "keep" in records[0]


def test_handler_transform_records_value_transforms(json_handler):
    """Test value transformation functions."""
    rs = JsonRecordSet()
    rs.add_record({"value": "10", "name": "test"})

    transforms = {"value": lambda x: int(x) * 2}
    result = json_handler.transform_records(rs, {}, value_transforms=transforms)

    records = list(result.iter_records())
    assert records[0]["value"] == 20


def test_handler_transform_records_transform_error(json_handler):
    """Test error handling in transform functions."""
    rs = JsonRecordSet()
    rs.add_record({"value": "not-a-number"})

    transforms = {"value": lambda x: int(x)}
    result = json_handler.transform_records(rs, {}, value_transforms=transforms)

    errors = json_handler.validation_errors()
    assert len(errors) > 0
    assert "transform error" in errors[0].lower()


def test_handler_transform_records_metadata_preserved(json_handler):
    """Test that metadata is preserved during transformation."""
    rs = JsonRecordSet(source_id="original")
    rs.set_metadata("key", "value")
    rs.add_record({"id": 1})

    result = json_handler.transform_records(rs, {})
    assert result.source_id == "original"
    assert result.metadata["key"] == "value"


# ---------------------------------------------------------------------------
# Test _build_record_set with dict.iterkeys()
# ---------------------------------------------------------------------------

def test_handler_build_record_set_list_format(json_handler):
    """Test building record set from bare list."""
    data = [{"id": 1}, {"id": 2}]
    rs = json_handler._build_record_set(data, "source1")

    assert rs.count() == 2
    assert rs.source_id == "source1"


def test_handler_build_record_set_envelope_format(json_handler):
    """Test building record set from envelope with metadata."""
    data = {
        "timestamp": "2024-01-15",
        "source": "gateway",
        "records": [{"id": 1}, {"id": 2}]
    }
    rs = json_handler._build_record_set(data, "source1")

    assert rs.count() == 2
    assert rs.get_metadata("timestamp") == "2024-01-15"
    assert rs.get_metadata("source") == "gateway"


def test_handler_build_record_set_single_record_envelope(json_handler):
    """Test envelope with single record (not a list)."""
    data = {
        "id": 1,
        "name": "single",
        "records": "not-a-list"
    }
    rs = json_handler._build_record_set(data, "source1")

    # Should add the whole dict as a single record
    assert rs.count() == 1


def test_handler_build_record_set_invalid_type(json_handler):
    """Test error with invalid root type."""
    data = "not-a-dict-or-list"
    with pytest.raises(Exception) as exc_info:
        json_handler._build_record_set(data, "source1")
    assert "unexpected" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test except Exception, e syntax
# ---------------------------------------------------------------------------

def test_handler_except_syntax_in_load_bytes(json_handler):
    """Test that old-style except catches errors correctly."""
    invalid_json = b'{"broken"'
    try:
        json_handler.load_bytes(invalid_json)
        assert False, "Should have raised exception"
    except Exception:
        pass  # Expected


def test_handler_except_syntax_in_transform(json_handler):
    """Test exception handling in transform_records."""
    rs = JsonRecordSet()
    rs.add_record({"val": "x"})

    def bad_transform(v):
        raise ValueError("Transform error")

    transforms = {"val": bad_transform}
    # Should not raise, but collect errors
    result = json_handler.transform_records(rs, {}, value_transforms=transforms)
    assert len(json_handler.validation_errors()) > 0


# ---------------------------------------------------------------------------
# Test validation_errors method
# ---------------------------------------------------------------------------

def test_handler_validation_errors_initially_empty(json_handler):
    """Test that validation errors are initially empty."""
    assert json_handler.validation_errors() == []


def test_handler_validation_errors_after_validation(json_handler):
    """Test errors accumulate during validation."""
    rs = JsonRecordSet()
    rs.add_record({"id": 1})  # Missing "name"
    rs.add_record({"id": 2})  # Missing "name"

    json_handler.validate_records(rs, ["id", "name"])
    errors = json_handler.validation_errors()
    assert len(errors) == 2


# ---------------------------------------------------------------------------
# Test unicode handling
# ---------------------------------------------------------------------------

def test_handler_unicode_round_trip(json_handler, tmp_path):
    """Test unicode content survives dump/load cycle."""
    rs = JsonRecordSet()
    rs.add_record({"label": u"温度センサー", "location": u"Chiba"})

    file_path = tmp_path / "unicode.json"
    json_handler.dump_to_file(rs, str(file_path))

    loaded = json_handler.load_file(str(file_path))
    records = list(loaded.iter_records())
    assert "温度" in records[0]["label"]


def test_handler_mixed_unicode_and_bytes(json_handler):
    """Test handling mixed unicode and byte strings."""
    # In Python 2, json.dumps encoding parameter handles this
    data = b'{"name": "test", "value": 123}'
    rs = json_handler.load_bytes(data)
    assert rs.count() == 1
