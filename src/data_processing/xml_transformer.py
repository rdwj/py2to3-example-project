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

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import xml.etree.ElementTree as ET
from HTMLParser import HTMLParser
import repr as reprlib_module

from core.exceptions import ParseError, DataError
from core.string_helpers import safe_decode, normalise_sensor_label
from core.config_loader import load_platform_config


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
        self._result.append(self.unescape(u"&%s;" % name))

    def handle_charref(self, name):
        self._result.append(self.unescape(u"&#%s;" % name))

    def get_text(self):
        return u"".join(self._result)


def unescape_html_entities(text):
    """Unescape HTML entities in *text* using HTMLParser.

    Returns a unicode string with all entities resolved.
    """
    if not isinstance(text, unicode):
        text = text.decode("utf-8", "replace")
    parser = _EntityUnescaper()
    parser.feed(text)
    parser.close()
    return parser.get_text()


# ---------------------------------------------------------------------------
# Debug output truncator using the repr module
# ---------------------------------------------------------------------------

_repr_formatter = reprlib_module.Repr()
_repr_formatter.maxstring = 80
_repr_formatter.maxother = 60


def _truncated_repr(obj):
    """Return a truncated repr of *obj* for debug logging.

    Uses the ``repr`` module (renamed to ``reprlib`` in Python 3) to
    limit output length when dumping large XML content to the log.
    """
    return _repr_formatter.repr(obj)


# ---------------------------------------------------------------------------
# XmlNodeMapper -- maps XML element paths to internal field names
# ---------------------------------------------------------------------------

class XmlNodeMapper(object):
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
        if self._element_maps.has_key(xpath):
            return self._element_maps[xpath]
        return None

    def get_attribute_mapping(self, element_path, attr_name):
        key = (element_path, attr_name)
        if self._attribute_maps.has_key(key):
            return self._attribute_maps[key]
        return None

    def get_text_mapping(self, xpath):
        if self._text_maps.has_key(xpath):
            return self._text_maps[xpath]
        return None


# ---------------------------------------------------------------------------
# XmlTransformer -- the main transform engine
# ---------------------------------------------------------------------------

class XmlTransformer(object):
    """Transform SCADA configuration XML into internal data structures.

    Parses the XML, walks the element tree, applies node mappings, and
    produces a list of configuration record dicts.
    """

    # Known SCADA namespace URIs -- the export format changed between
    # Experion R400 and R500 and uses different namespace prefixes
    NAMESPACE_R400 = u"http://honeywell.com/experion/r400/tagdb"
    NAMESPACE_R500 = u"http://honeywell.com/experion/r500/tagdb"

    def __init__(self, node_mapper=None):
        self._node_mapper = node_mapper or XmlNodeMapper()
        self._config = load_platform_config()
        self._transform_errors = []

    def transform_file(self, xml_path, root_element=None):
        """Parse an XML file and transform it into config records."""
        print "Loading XML from %s" % xml_path

        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Detect namespace from root element
        namespace = self._detect_namespace(root)
        if namespace:
            print "Detected SCADA namespace: %s" % namespace

        if root_element is not None:
            root = root.find(root_element)
            if root is None:
                raise ParseError(
                    "Root element '%s' not found in %s" % (root_element, xml_path)
                )

        records = self._transform_element(root, "", namespace)
        print "Transformed %d records from %s" % (len(records), xml_path)

        if self._transform_errors:
            print "Transform errors: %d" % len(self._transform_errors)
            for err in self._transform_errors[:10]:
                print "  %s" % err

        return records

    def transform_string(self, xml_string):
        """Parse XML from a string and transform it."""
        if isinstance(xml_string, unicode):
            xml_string = xml_string.encode("utf-8")
        root = ET.fromstring(xml_string)
        namespace = self._detect_namespace(root)
        return self._transform_element(root, "", namespace)

    def _detect_namespace(self, element):
        """Extract the namespace URI from an element's tag, if present."""
        tag = element.tag
        if isinstance(tag, str):
            tag = tag.decode("utf-8", "replace")
        if tag.startswith(u"{"):
            ns_end = tag.find(u"}")
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

            # Unicode string comparison for attribute matching
            if isinstance(attr_value, str):
                attr_value = attr_value.decode("utf-8", "replace")

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
                except Exception, e:
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
            if isinstance(text, str):
                text = text.decode("utf-8", "replace")
            text = unescape_html_entities(text.strip())

            text_mapping = self._node_mapper.get_text_mapping(element_path)
            if text_mapping is not None:
                try:
                    value = text
                    if text_mapping["transform"] is not None:
                        value = text_mapping["transform"](value)
                    record[text_mapping["name"]] = value
                except Exception, e:
                    self._transform_errors.append(
                        "Text at %s: %s (raw=%s)" % (
                            element_path, str(e), _truncated_repr(text),
                        )
                    )

        # Normalise sensor labels if present (handles Japanese kanji etc.)
        if record.has_key(u"description"):
            record[u"description"] = normalise_sensor_label(record[u"description"])

        if not record or (len(record) == 1 and record.has_key("_type")):
            return None
        return record

    def _strip_namespace(self, tag, namespace):
        """Remove the namespace prefix from an element tag."""
        if isinstance(tag, str):
            tag = tag.decode("utf-8", "replace")
        if namespace and tag.startswith(u"{%s}" % namespace):
            return tag[len(namespace) + 2:]
        return tag

    def errors(self):
        return list(self._transform_errors)
