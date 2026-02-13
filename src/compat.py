# -*- coding: utf-8 -*-
"""
Internal compatibility layer for the Legacy Industrial Data Platform.

Simplified for Python 3 -- all Py2/3 branching removed.  Provides
canonical aliases so that any remaining consumers can import from here
without change.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import sys

PY3 = True

# ------------------------------------------------------------------
# String / bytes type aliases
# ------------------------------------------------------------------
string_types = (str,)
text_type = str
binary_type = bytes
integer_types = (int,)

# ------------------------------------------------------------------
# OrderedDict -- builtin since Python 3.1
# ------------------------------------------------------------------
from collections import OrderedDict

# ------------------------------------------------------------------
# json
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
# io
# ------------------------------------------------------------------
from io import BytesIO, StringIO


def ensure_bytes(value, encoding="utf-8"):
    """Coerce *value* to a byte string."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode(encoding)
    return str(value).encode(encoding)


def ensure_text(value, encoding="utf-8"):
    """Coerce *value* to a text string."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode(encoding)
    return str(value)
