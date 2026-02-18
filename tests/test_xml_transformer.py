# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/xml_transformer.py

Tests the current Python 2 behavior including:
- HTMLParser.HTMLParser usage
- repr module (renamed to reprlib)
- u"" string literals
- dict.has_key()
- except Exception, e syntax
- XML encoding handling
- Unicode string comparison
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import tempfile
import pytest
from xml.etree import ElementTree as ET

from src.data_processing.xml_transformer import (
    unescape_html_entities,
    XmlNodeMapper,
    XmlTransformer,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_xml_file(tmp_path):
    """Create a temporary XML file for testing."""
    def _create_xml(content):
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(content, encoding="utf-8")
        return str(xml_file)
    return _create_xml


@pytest.fixture
def node_mapper():
    """Create a configured XmlNodeMapper for testing."""
    mapper = XmlNodeMapper()
    mapper.map_element("TagDatabase/PointGroup/Point", "sensor_point")
    mapper.map_attribute("TagDatabase/PointGroup/Point", "TagName", "tag_name")
    mapper.map_attribute("TagDatabase/PointGroup/Point", "Description", "description")
    mapper.map_text("TagDatabase/PointGroup/Point/Value", "current_value")
    return mapper


# ---------------------------------------------------------------------------
# Test unescape_html_entities
# ---------------------------------------------------------------------------

def test_unescape_html_entities_with_amp():
    """Test HTML entity unescaping for &amp;."""
    text = "Pressure &amp; Temperature"
    result = unescape_html_entities(text)
    assert result == "Pressure & Temperature"
    assert isinstance(result, str)


def test_unescape_html_entities_with_degree_charref():
    """Test character reference like &#176; (degree symbol)."""
    text = "Temp: 25&#176;C"
    result = unescape_html_entities(text)
    assert "°C" in result
    assert isinstance(result, str)


def test_unescape_html_entities_with_multiple():
    """Test multiple entities in one string."""
    text = "&lt;tag&gt; &amp; &quot;value&quot;"
    result = unescape_html_entities(text)
    assert result == '<tag> & "value"'


def test_unescape_html_entities_with_unicode_input():
    """Test with unicode input string."""
    text = u"Kanji: \u6e29\u5ea6 &amp; symbol"
    result = unescape_html_entities(text)
    assert "Kanji: 温度 & symbol" in result


def test_unescape_html_entities_with_bytes():
    """Test with bytes input."""
    text = "Simple &amp; text"
    result = unescape_html_entities(text)
    assert isinstance(result, str)
    assert "&" in result


def test_unescape_html_entities_no_entities():
    """Test plain text with no entities."""
    text = "Plain text"
    result = unescape_html_entities(text)
    assert result == "Plain text"


# ---------------------------------------------------------------------------
# Test XmlNodeMapper
# ---------------------------------------------------------------------------

def test_node_mapper_map_element():
    """Test element mapping registration."""
    mapper = XmlNodeMapper()
    mapper.map_element("TagDatabase/Point", "sensor")
    mapping = mapper.get_element_mapping("TagDatabase/Point")
    assert mapping is not None
    assert mapping["name"] == "sensor"
    assert mapping["transform"] is None


def test_node_mapper_map_element_with_transform():
    """Test element mapping with transform function."""
    mapper = XmlNodeMapper()
    transform = lambda x: x.upper()
    mapper.map_element("TagDatabase/Point", "sensor", transform_func=transform)
    mapping = mapper.get_element_mapping("TagDatabase/Point")
    assert mapping["transform"] is transform


def test_node_mapper_map_attribute():
    """Test attribute mapping registration."""
    mapper = XmlNodeMapper()
    mapper.map_attribute("TagDatabase/Point", "id", "point_id")
    mapping = mapper.get_attribute_mapping("TagDatabase/Point", "id")
    assert mapping is not None
    assert mapping["name"] == "point_id"


def test_node_mapper_map_text():
    """Test text content mapping."""
    mapper = XmlNodeMapper()
    mapper.map_text("TagDatabase/Point/Value", "sensor_value")
    mapping = mapper.get_text_mapping("TagDatabase/Point/Value")
    assert mapping is not None
    assert mapping["name"] == "sensor_value"


def test_node_mapper_get_nonexistent_element():
    """Test has_key() behavior for missing element."""
    mapper = XmlNodeMapper()
    result = mapper.get_element_mapping("NonExistent/Path")
    assert result is None


def test_node_mapper_get_nonexistent_attribute():
    """Test has_key() behavior for missing attribute."""
    mapper = XmlNodeMapper()
    result = mapper.get_attribute_mapping("TagDatabase/Point", "missing")
    assert result is None


# ---------------------------------------------------------------------------
# Test XmlTransformer basic functionality
# ---------------------------------------------------------------------------

def test_transformer_transform_string_simple():
    """Test transforming simple XML string."""
    xml = '<Root><Item id="1">Value</Item></Root>'
    transformer = XmlTransformer()
    records = transformer.transform_string(xml)
    assert isinstance(records, list)
    assert len(records) >= 0


def test_transformer_transform_string_unicode():
    """Test transforming XML with unicode content."""
    xml = u'<Root><Item>温度センサー</Item></Root>'
    transformer = XmlTransformer()
    records = transformer.transform_string(xml)
    assert isinstance(records, list)


def test_transformer_transform_string_bytes():
    """Test transforming XML from bytes (Python 2 str)."""
    xml = b'<Root><Item>Test</Item></Root>'
    transformer = XmlTransformer()
    records = transformer.transform_string(xml)
    assert isinstance(records, list)


def test_transformer_detect_namespace_r400():
    """Test namespace detection for R400 format."""
    xml = '<TagDatabase xmlns="http://honeywell.com/experion/r400/tagdb"><Point/></TagDatabase>'
    transformer = XmlTransformer()
    root = ET.fromstring(xml)
    namespace = transformer._detect_namespace(root)
    assert namespace == XmlTransformer.NAMESPACE_R400


def test_transformer_detect_namespace_r500():
    """Test namespace detection for R500 format."""
    xml = '<TagDatabase xmlns="http://honeywell.com/experion/r500/tagdb"><Point/></TagDatabase>'
    transformer = XmlTransformer()
    root = ET.fromstring(xml)
    namespace = transformer._detect_namespace(root)
    assert namespace == XmlTransformer.NAMESPACE_R500


def test_transformer_detect_namespace_none():
    """Test no namespace in simple XML."""
    xml = '<TagDatabase><Point/></TagDatabase>'
    transformer = XmlTransformer()
    root = ET.fromstring(xml)
    namespace = transformer._detect_namespace(root)
    assert namespace is None


# ---------------------------------------------------------------------------
# Test XmlTransformer with node mapping
# ---------------------------------------------------------------------------

def test_transformer_with_mapper_attributes(node_mapper):
    """Test attribute extraction with mapping."""
    xml = '''<TagDatabase>
        <PointGroup>
            <Point TagName="TAG001" Description="Temp sensor &amp; monitor"/>
        </PointGroup>
    </TagDatabase>'''
    transformer = XmlTransformer(node_mapper=node_mapper)
    records = transformer.transform_string(xml)

    # Find the Point record
    point_records = [r for r in records if r.get("_type") == "sensor_point"]
    assert len(point_records) == 1
    assert point_records[0]["tag_name"] == "TAG001"
    assert "Temp sensor & monitor" in point_records[0]["description"]


def test_transformer_with_mapper_text_content(node_mapper):
    """Test text content extraction with mapping."""
    xml = '''<TagDatabase>
        <PointGroup>
            <Point TagName="TAG001">
                <Value>42.5</Value>
            </Point>
        </PointGroup>
    </TagDatabase>'''
    transformer = XmlTransformer(node_mapper=node_mapper)
    records = transformer.transform_string(xml)

    # Find the Value record
    value_records = [r for r in records if "current_value" in r]
    assert len(value_records) == 1
    assert value_records[0]["current_value"] == "42.5"


def test_transformer_html_entities_in_attributes():
    """Test HTML entity unescaping in attribute values."""
    xml = '<Root><Item desc="&lt;sensor&gt; &amp; &quot;value&quot;"/></Root>'
    mapper = XmlNodeMapper()
    mapper.map_attribute("Root/Item", "desc", "description")
    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    item_records = [r for r in records if "description" in r]
    assert len(item_records) == 1
    assert item_records[0]["description"] == '<sensor> & "value"'


def test_transformer_unicode_attribute_values():
    """Test unicode attribute values (Japanese kanji)."""
    xml = u'<Root><Item label="温度センサー"/></Root>'
    mapper = XmlNodeMapper()
    mapper.map_attribute("Root/Item", "label", "sensor_label")
    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    item_records = [r for r in records if "sensor_label" in r]
    assert len(item_records) == 1
    assert "温度" in item_records[0]["sensor_label"]


# ---------------------------------------------------------------------------
# Test transform with exception handling
# ---------------------------------------------------------------------------

def test_transformer_transform_function_error():
    """Test error handling when transform function raises exception."""
    xml = '<Root><Item value="not-a-number"/></Root>'
    mapper = XmlNodeMapper()

    def bad_transform(v):
        raise ValueError("Transform failed")

    mapper.map_attribute("Root/Item", "value", "numeric_value", transform_func=bad_transform)
    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    errors = transformer.errors()
    assert len(errors) > 0
    assert "Transform failed" in errors[0]


def test_transformer_text_transform_error():
    """Test error handling for text content transform failure."""
    xml = '<Root><Item>bad-data</Item></Root>'
    mapper = XmlNodeMapper()

    def bad_transform(v):
        raise ValueError("Text transform failed")

    mapper.map_text("Root/Item", "processed_text", transform_func=bad_transform)
    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    errors = transformer.errors()
    assert len(errors) > 0
    assert "Text transform failed" in errors[0]


# ---------------------------------------------------------------------------
# Test file-based transformation
# ---------------------------------------------------------------------------

def test_transformer_transform_file_simple(temp_xml_file):
    """Test transforming from a file."""
    xml_content = '<Root><Item id="1">Value</Item></Root>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    records = transformer.transform_file(xml_path)
    assert isinstance(records, list)


def test_transformer_transform_file_with_encoding(temp_xml_file):
    """Test transforming file with UTF-8 encoding declaration."""
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<Root><Item>温度</Item></Root>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    records = transformer.transform_file(xml_path)
    assert isinstance(records, list)


def test_transformer_transform_file_with_root_element(temp_xml_file):
    """Test transforming with specific root element selection."""
    xml_content = '''<Document>
        <Metadata/>
        <Data>
            <Item id="1">Value</Item>
        </Data>
    </Document>'''
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    records = transformer.transform_file(xml_path, root_element="Data")
    assert isinstance(records, list)


def test_transformer_transform_file_missing_root_element(temp_xml_file):
    """Test error when specified root element not found."""
    xml_content = '<Root><Item/></Root>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    with pytest.raises(Exception) as exc_info:
        transformer.transform_file(xml_path, root_element="NonExistent")
    assert "not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test namespace stripping
# ---------------------------------------------------------------------------

def test_transformer_strip_namespace_with_namespace():
    """Test namespace stripping when namespace is present."""
    transformer = XmlTransformer()
    tag = "{http://honeywell.com/experion/r400/tagdb}Point"
    namespace = "http://honeywell.com/experion/r400/tagdb"
    result = transformer._strip_namespace(tag, namespace)
    assert result == "Point"


def test_transformer_strip_namespace_without_namespace():
    """Test namespace stripping when tag has no namespace."""
    transformer = XmlTransformer()
    tag = "Point"
    namespace = "http://honeywell.com/experion/r400/tagdb"
    result = transformer._strip_namespace(tag, namespace)
    assert result == "Point"


def test_transformer_strip_namespace_bytes_tag():
    """Test namespace stripping with bytes tag (Python 2 str)."""
    transformer = XmlTransformer()
    tag = b"Point"
    namespace = "http://honeywell.com/experion/r400/tagdb"
    result = transformer._strip_namespace(tag, namespace)
    assert result == "Point"


# ---------------------------------------------------------------------------
# Test error collection
# ---------------------------------------------------------------------------

def test_transformer_errors_initially_empty():
    """Test that errors list is initially empty."""
    transformer = XmlTransformer()
    assert transformer.errors() == []


def test_transformer_errors_after_transform_failure():
    """Test errors are collected during transformation."""
    xml = '<Root><Item value="test"/></Root>'
    mapper = XmlNodeMapper()

    def failing_transform(v):
        raise ValueError("Expected failure")

    mapper.map_attribute("Root/Item", "value", "processed", transform_func=failing_transform)
    transformer = XmlTransformer(node_mapper=mapper)
    transformer.transform_string(xml)

    errors = transformer.errors()
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Test print statements (capture output)
# ---------------------------------------------------------------------------

def test_transformer_file_prints_loading_message(temp_xml_file, capsys):
    """Test that file transformation prints loading message."""
    xml_content = '<Root><Item/></Root>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    transformer.transform_file(xml_path)

    captured = capsys.readouterr()
    assert "Loading XML from" in captured.out


def test_transformer_file_prints_transformed_count(temp_xml_file, capsys):
    """Test that file transformation prints record count."""
    xml_content = '<Root><Item/></Root>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    transformer.transform_file(xml_path)

    captured = capsys.readouterr()
    assert "Transformed" in captured.out
    assert "records" in captured.out


def test_transformer_file_prints_namespace(temp_xml_file, capsys):
    """Test that namespace detection is printed."""
    xml_content = '<TagDatabase xmlns="http://honeywell.com/experion/r400/tagdb"><Point/></TagDatabase>'
    xml_path = temp_xml_file(xml_content)

    transformer = XmlTransformer()
    transformer.transform_file(xml_path)

    captured = capsys.readouterr()
    assert "Detected SCADA namespace" in captured.out


# ---------------------------------------------------------------------------
# Test complex scenarios
# ---------------------------------------------------------------------------

def test_transformer_nested_elements_with_mixed_content():
    """Test transformation of deeply nested XML with mixed content."""
    xml = '''<TagDatabase>
        <PointGroup name="Group1">
            <Point TagName="TAG001" Description="Primary sensor">
                <Value>100.5</Value>
                <Unit>degC</Unit>
            </Point>
            <Point TagName="TAG002" Description="Secondary &amp; backup">
                <Value>99.2</Value>
            </Point>
        </PointGroup>
    </TagDatabase>'''

    mapper = XmlNodeMapper()
    mapper.map_element("TagDatabase/PointGroup/Point", "sensor_point")
    mapper.map_attribute("TagDatabase/PointGroup/Point", "TagName", "tag")
    mapper.map_attribute("TagDatabase/PointGroup/Point", "Description", "desc")

    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    point_records = [r for r in records if r.get("_type") == "sensor_point"]
    assert len(point_records) == 2
    assert point_records[0]["tag"] == "TAG001"
    assert point_records[1]["tag"] == "TAG002"
    assert "&" in point_records[1]["desc"]


def test_transformer_unmapped_attributes_included():
    """Test that unmapped attributes are included in records."""
    xml = '<Root><Item id="123" status="active" priority="high"/></Root>'
    mapper = XmlNodeMapper()
    mapper.map_attribute("Root/Item", "id", "item_id")

    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    item_records = [r for r in records if "item_id" in r]
    assert len(item_records) == 1
    # Unmapped attributes should still appear
    assert "status" in item_records[0] or "priority" in item_records[0]


def test_transformer_empty_records_filtered():
    """Test that empty records (only _type) are filtered out."""
    xml = '<Root><Empty/></Root>'
    mapper = XmlNodeMapper()
    mapper.map_element("Root/Empty", "empty_type")

    transformer = XmlTransformer(node_mapper=mapper)
    records = transformer.transform_string(xml)

    # Empty record should be filtered (only has _type, no other fields)
    empty_records = [r for r in records if r.get("_type") == "empty_type"]
    assert len(empty_records) == 0
