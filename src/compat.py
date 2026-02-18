# -*- coding: utf-8 -*-
"""
Internal compatibility layer for the Legacy Industrial Data Platform.

This module has been converted to Python 3-only, but is retained for
API compatibility. It provides type aliases and utility functions that
other modules may still import. The Python 2 compatibility shims have
been removed.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys

PY26 = False
PY27 = False

# ------------------------------------------------------------------
# String / bytes type aliases
# ------------------------------------------------------------------
string_types = (str,)
text_type = str
binary_type = bytes
integer_types = (int,)

# ------------------------------------------------------------------
# OrderedDict -- builtin in Python 3
# ------------------------------------------------------------------
from collections import OrderedDict

# ------------------------------------------------------------------
# json -- stdlib json module
# ------------------------------------------------------------------
import json

# ------------------------------------------------------------------
# hashlib
# ------------------------------------------------------------------
from hashlib import md5, sha1

# ------------------------------------------------------------------
# configparser
# ------------------------------------------------------------------
import configparser

# ------------------------------------------------------------------
# queue
# ------------------------------------------------------------------
import queue

# ------------------------------------------------------------------
# pickle
# ------------------------------------------------------------------
import pickle

# ------------------------------------------------------------------
# StringIO / BytesIO
# ------------------------------------------------------------------
from io import BytesIO
from io import StringIO


def ensure_bytes(value, encoding="utf-8"):
    """Coerce *value* to a byte string."""
    if isinstance(value, str):
        return value.encode(encoding)
    if isinstance(value, bytes):
        return value
    return str(value).encode(encoding)


def ensure_text(value, encoding="utf-8"):
    """Coerce *value* to a text string."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode(encoding)
    return str(value)
