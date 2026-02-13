# -*- coding: utf-8 -*-
"""
Data processing subsystem for the Legacy Industrial Data Platform.

This package handles ingestion, parsing, and transformation of data from
multiple external sources: mainframe batch transfers, CSV exports from
historians, SCADA XML configurations, JSON feeds from REST gateways,
unstructured text from maintenance logs, and structured log files from
plant control systems.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from mainframe_parser import MainframeParser, CopybookLayout, MainframeRecord
from csv_processor import CsvProcessor, CsvFieldMapper
from xml_transformer import XmlTransformer, XmlNodeMapper
from json_handler import JsonHandler, JsonRecordSet
from text_analyzer import TextAnalyzer, TextFingerprint
from log_parser import LogParser, LogEntry, LogFilter
