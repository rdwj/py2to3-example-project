# -*- coding: utf-8 -*-
"""
Core data types and utilities for the Legacy Industrial Data Platform.
"""

from types import DataPoint, SensorReading, LargeCounter
from exceptions import PlatformError, ProtocolError, DataError, StorageError
from config_loader import load_platform_config
