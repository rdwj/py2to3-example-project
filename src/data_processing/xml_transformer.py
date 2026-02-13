# -*- coding: utf-8 -*-
"""
XML transformer for SCADA configuration files.

The SCADA system (Honeywell Experion) exports its tag database and alarm
configuration as XML documents.  These files contain a mix of ASCII tag
identifiers and unicode descriptions (the Japanese facility uses kanji
in alarm text).  Some fields also contain HTML entities from the SCADA
web interface that need to be unescaped before processing.

This transformer reads the SCADA XML, maps nodes to internal data
structures, and produces the configuration dicts consumed by the
real-time alarm processing engine.
"""


import os
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import reprlib as reprlib_module

from src.core.exceptions import ParseError, DataError
from src.core.string_helpers import safe_decode, normalise_sensor_label
from src.core.config_loader import load_platform_config


# ---------------------------------------------------------------------------
# HTML entity unescaper -- reuses the stdlib HTMLParser for this job
# ---------------------------------------------------------------------------

class _EntityUnescaper(HTMLParser):
    """Minimal HTMLParser subclass used solely to unescape HTML entities
    found in SCADA XML attribute values.

    The SCADA web interface HTML-encodes special characters in alarm
    descriptions (e.g. ``&amp;``, ``&#176;`` for the degree symbol),
    and those entities end up in the exported XML.
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self._result = []

    def handle_data(self, data):
        self._result.append(data)

    def handle_entityref(self, name):
        from html import unescape
        self._result.append(unescape("&%s;" % name))

    def handle_charref(self, name):
        from html import unescape
        self._result.append(unescape("&#%s;" % name))

    def get_text(self):
        return "".join(self._result)


def unescape_html_entities(text):
    """Unescape HTML entities in *text* using HTMLParser.

    Returns a string with all entities resolved.
    """
    if not isinstance(text, str):
        text = text.decode("utf-8", "replace")
    parser = _EntityUnescaper()
    parser.feed(text)
    parser.close()
    return parser.get_text()


# ---------------------------------------------------------------------------
# Debug output truncator using the reprlib module
# ---------------------------------------------------------------------------

_repr_formatter = reprlib_module.Repr()
_repr_formatter.maxstring = 80
_repr_formatter.maxother = 60


def _truncated_repr(obj):
    """Return a truncated repr of *obj* for debug logging.

    Uses the ``reprlib`` module to limit output length when dumping
    large XML content to the log.
    """
    return _repr_formatter.repr(obj)


# ---------------------------------------------------------------------------
# XmlNodeMapper -- maps XML element paths to internal field names
# ---------------------------------------------------------------------------

class XmlNodeMapper:
    """Maps SCADA XML element paths and attributes to internal field names.

    The SCADA export uses deeply nested paths like:
        /TagDatabase/PointGroup/Point/@TagName
    which we flatten into simple internal names like 'tag_name'.
    """

    def __init__(self):
        self._element_maps = {}
        self._attribute_maps = {}
        self._text_maps = {}

    def map_element(self, xpath, internal_name, transform_func=None):
        """Register an element-path-to-field mapping."""
        self._element_maps[xpath] = {
            "name": internal_name,
            "transform": transform_func,
        }

    def map_attribute(self, element_path, attr_name, internal_name,
                      transform_func=None):
        """Register an attribute mapping within a specific element."""
        key = (element_path, attr_name)
        self._attribute_maps[key] = {
            "name": internal_name,
            "transform": transform_func,
        }

    def map_text(self, xpath, internal_name, transform_func=None):
        """Register a text-content mapping for a leaf element."""
        self._text_maps[xpath] = {
            "name": internal_name,
            "transform": transform_func,
        }

    def get_element_mapping(self, xpath):
        if xpath in self._element_maps:
            return self._element_maps[xpath]
        return None

    def get_attribute_mapping(self, element_path, attr_name):
        key = (element_path, attr_name)
        if key in self._attribute_maps:
            return self._attribute_maps[key]
        return None

    def get_text_mapping(self, xpath):
        if xpath in self._text_maps:
            return self._text_maps[xpath]
        return None


# ---------------------------------------------------------------------------
# XmlTransformer -- the main transform engine
# ---------------------------------------------------------------------------

class XmlTransformer:
    """Transform SCADA configuration XML into internal data structures.

    Parses the XML, walks the element tree, applies node mappings, and
    produces a list of configuration record dicts.
    """

    # Known SCADA namespace URIs -- the export format changed between
    # Experion R400 and R500 and uses different namespace prefixes
    NAMESPACE_R400 = "http://honeywell.com/experion/r400/tagdb"
    NAMESPACE_R500 = "http://honeywell.com/experion/r500/tagdb"

    def __init__(self, node_mapper=None):
        self._node_mapper = node_mapper or XmlNodeMapper()
        self._config = load_platform_config()
        self._transform_errors = []

    def transform_file(self, xml_path, root_element=None):
        """Parse an XML file and transform it into config records."""
        print("Loading XML from %s" % xml_path)

        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Detect namespace from root element
        namespace = self._detect_namespace(root)
        if namespace:
            print("Detected SCADA namespace: %s" % namespace)

        if root_element is not None:
            root = root.find(root_element)
            if root is None:
                raise ParseError(
                    "Root element '%s' not found in %s" % (root_element, xml_path)
                )

        records = self._transform_element(root, "", namespace)
        print("Transformed %d records from %s" % (len(records), xml_path))

        if self._transform_errors:
            print("Transform errors: %d" % len(self._transform_errors))
            for err in self._transform_errors[:10]:
                print("  %s" % err)

        return records

    def transform_string(self, xml_string):
        """Parse XML from a string and transform it."""
        if isinstance(xml_string, str):
            xml_string = xml_string.encode("utf-8")
        root = ET.fromstring(xml_string)
        namespace = self._detect_namespace(root)
        return self._transform_element(root, "", namespace)

    def _detect_namespace(self, element):
        """Extract the namespace URI from an element's tag, if present."""
        tag = element.tag
        if tag.startswith("{"):
            ns_end = tag.find("}")
            if ns_end > 0:
                return tag[1:ns_end]
        return None

    def _transform_element(self, element, parent_path, namespace):
        """Recursively transform an element and its children into records."""
        records = []
        tag_name = self._strip_namespace(element.tag, namespace)
        current_path = "%s/%s" % (parent_path, tag_name) if parent_path else tag_name

        record = self._extract_record(element, current_path, namespace)
        if record:
            records.append(record)

        for child in element:
            child_records = self._transform_element(child, current_path, namespace)
            records.extend(child_records)

        return records

    def _extract_record(self, element, element_path, namespace):
        """Extract field values from a single element."""
        record = {}

        # Check if the element itself is mapped
        elem_mapping = self._node_mapper.get_element_mapping(element_path)
        if elem_mapping is not None:
            record["_type"] = elem_mapping["name"]

        # Extract mapped attributes
        for attr_name, attr_value in element.attrib.items():
            attr_name_clean = self._strip_namespace(attr_name, namespace)

            # Unescape any HTML entities in attribute values
            attr_value = unescape_html_entities(attr_value)

            mapping = self._node_mapper.get_attribute_mapping(
                element_path, attr_name_clean,
            )
            if mapping is not None:
                try:
                    value = attr_value
                    if mapping["transform"] is not None:
                        value = mapping["transform"](value)
                    record[mapping["name"]] = value
                except Exception as e:
                    self._transform_errors.append(
                        "Attribute %s@%s: %s (raw=%s)" % (
                            element_path, attr_name_clean, str(e),
                            _truncated_repr(attr_value),
                        )
                    )
            elif attr_name_clean and record:
                # Include unmapped attributes as-is for unrecognised fields
                record[attr_name_clean] = attr_value

        # Extract mapped text content
        text = element.text
        if text is not None:
            text = unescape_html_entities(text.strip())

            text_mapping = self._node_mapper.get_text_mapping(element_path)
            if text_mapping is not None:
                try:
                    value = text
                    if text_mapping["transform"] is not None:
                        value = text_mapping["transform"](value)
                    record[text_mapping["name"]] = value
                except Exception as e:
                    self._transform_errors.append(
                        "Text at %s: %s (raw=%s)" % (
                            element_path, str(e), _truncated_repr(text),
                        )
                    )

        # Normalise sensor labels if present (handles Japanese kanji etc.)
        if "description" in record:
            record["description"] = normalise_sensor_label(record["description"])

        if not record or (len(record) == 1 and "_type" in record):
            return None
        return record

    def _strip_namespace(self, tag, namespace):
        """Remove the namespace prefix from an element tag."""
        if namespace and tag.startswith("{%s}" % namespace):
            return tag[len(namespace) + 2:]
        return tag

    def errors(self):
        return list(self._transform_errors)
