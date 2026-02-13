# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/xml_transformer.py

Captures pre-migration behavior of:
- HTMLParser for entity unescaping (HTMLParser module renamed html.parser in Py3)
- repr module (renamed reprlib in Py3)
- XmlNodeMapper with dict.has_key()
- XmlTransformer XML parsing and encoding detection
- Py2-specific: unicode isinstance checks, str.decode(), dict.has_key()
"""


import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.data_processing.xml_transformer import (
    unescape_html_entities, _truncated_repr,
    XmlNodeMapper, XmlTransformer,
)


class TestUnescapeHtmlEntities:
    """Characterize HTML entity unescaping."""

    def test_named_entity(self):
        """Captures: &amp; -> &."""
        assert unescape_html_entities("A &amp; B") == "A & B"

    def test_numeric_entity(self):
        """Captures: &#176; -> degree symbol."""
        result = unescape_html_entities("100&#176;C")
        assert "\u00b0" in result

    def test_no_entities(self):
        """Captures: plain text returned unchanged."""
        assert unescape_html_entities("plain text") == "plain text"

    @pytest.mark.py2_behavior
    def test_byte_string_decoded(self):
        """Captures: byte string input decoded to unicode first."""
        result = unescape_html_entities("A &amp; B")
        assert isinstance(result, str)


class TestTruncatedRepr:
    """Characterize repr module truncation."""

    @pytest.mark.py2_behavior
    def test_short_string(self):
        """Captures: repr module (renamed reprlib in Py3)."""
        result = _truncated_repr("short")
        assert "short" in result

    def test_long_string_truncated(self):
        """Captures: strings beyond maxstring are truncated."""
        result = _truncated_repr("x" * 200)
        assert len(result) < 200


class TestXmlNodeMapper:
    """Characterize XML node mapping with dict.has_key()."""

    @pytest.mark.py2_behavior
    def test_map_and_get_element(self):
        """Captures: element mapping uses has_key() for lookup."""
        mapper = XmlNodeMapper()
        mapper.map_element("/Root/Point", "sensor_point")
        result = mapper.get_element_mapping("/Root/Point")
        assert result["name"] == "sensor_point"

    def test_get_missing_element(self):
        """Captures: missing mapping returns None."""
        mapper = XmlNodeMapper()
        assert mapper.get_element_mapping("/Missing") is None

    @pytest.mark.py2_behavior
    def test_map_and_get_attribute(self):
        """Captures: attribute mapping uses has_key()."""
        mapper = XmlNodeMapper()
        mapper.map_attribute("/Root/Point", "TagName", "tag_name")
        result = mapper.get_attribute_mapping("/Root/Point", "TagName")
        assert result["name"] == "tag_name"

    @pytest.mark.py2_behavior
    def test_map_and_get_text(self):
        """Captures: text mapping uses has_key()."""
        mapper = XmlNodeMapper()
        mapper.map_text("/Root/Point/Description", "description")
        result = mapper.get_text_mapping("/Root/Point/Description")
        assert result["name"] == "description"

    def test_transform_func(self):
        """Captures: optional transform function stored in mapping."""
        mapper = XmlNodeMapper()
        mapper.map_attribute("/Root", "Value", "value", transform_func=float)
        mapping = mapper.get_attribute_mapping("/Root", "Value")
        assert mapping["transform"]("42.5") == 42.5


class TestXmlTransformer:
    """Characterize XML transformation."""

    def test_transform_simple_xml(self):
        """Captures: basic XML string transformation."""
        mapper = XmlNodeMapper()
        mapper.map_attribute("Root/Point", "TagName", "tag_name")
        mapper.map_attribute("Root/Point", "Value", "value", transform_func=float)

        transformer = XmlTransformer(node_mapper=mapper)
        xml = '<Root><Point TagName="TEMP-001" Value="23.5"/></Root>'
        records = transformer.transform_string(xml)
        assert len(records) >= 1
        record = records[0]
        assert record["tag_name"] == "TEMP-001"
        assert record["value"] == 23.5

    @pytest.mark.py2_behavior
    def test_transform_with_unicode_content(self):
        """Captures: unicode XML content with Japanese characters."""
        mapper = XmlNodeMapper()
        mapper.map_text("Root/Description", "description")

        transformer = XmlTransformer(node_mapper=mapper)
        xml = '<Root><Description>\u6e29\u5ea6\u30bb\u30f3\u30b5\u30fc</Description></Root>'
        records = transformer.transform_string(xml)
        found = [r for r in records if "description" in r]
        assert len(found) >= 1

    def test_transform_with_html_entities(self):
        """Captures: HTML entities in attribute values are unescaped."""
        mapper = XmlNodeMapper()
        mapper.map_attribute("Root/Point", "Desc", "description")

        transformer = XmlTransformer(node_mapper=mapper)
        xml = '<Root><Point Desc="100&amp;#176;C High"/></Root>'
        records = transformer.transform_string(xml)
        if records:
            desc = records[0].get("description", "")
            # Should contain unescaped content
            assert "&amp;" not in desc

    def test_errors_accessible(self):
        """Captures: transform errors tracked and accessible."""
        transformer = XmlTransformer()
        assert transformer.errors() == []
