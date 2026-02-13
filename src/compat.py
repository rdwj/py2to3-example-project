# -*- coding: utf-8 -*-
"""
Internal compatibility layer for the Legacy Industrial Data Platform.

Centralizes version-sensitive imports and type aliases so that other
modules can import from here instead of scattering try/except blocks
everywhere.  In practice this module was added late in the project
lifecycle when someone floated the idea of a Python 3 port -- most of
the codebase still uses Py2 idioms directly.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import sys

PY26 = sys.version_info[:2] == (2, 6)
PY27 = sys.version_info[:2] == (2, 7)

# ------------------------------------------------------------------
# String / bytes type aliases
# ------------------------------------------------------------------
string_types = (str, unicode)
text_type = unicode
binary_type = str
integer_types = (int, long)

# ------------------------------------------------------------------
# OrderedDict -- backported for 2.6, builtin in 2.7
# ------------------------------------------------------------------
try:
    from collections import OrderedDict
except ImportError:
    # Python 2.6 fallback -- use the ordereddict backport if installed,
    # otherwise provide a minimal shim that just wraps a regular dict.
    try:
        from ordereddict import OrderedDict
    except ImportError:
        OrderedDict = dict

# ------------------------------------------------------------------
# json -- simplejson is faster and has better unicode handling on 2.6
# ------------------------------------------------------------------
try:
    import simplejson as json
except ImportError:
    import json

# ------------------------------------------------------------------
# hashlib vs legacy md5/sha modules
# ------------------------------------------------------------------
try:
    from hashlib import md5, sha1
except ImportError:
    from md5 import new as md5
    from sha import new as sha1

# ------------------------------------------------------------------
# ConfigParser -- capital-C in Py2, lowercase in Py3
# ------------------------------------------------------------------
try:
    import ConfigParser as configparser
except ImportError:
    import configparser

# ------------------------------------------------------------------
# Queue -- capital-Q in Py2
# ------------------------------------------------------------------
try:
    import Queue as queue
except ImportError:
    import queue

# ------------------------------------------------------------------
# cPickle / pickle
# ------------------------------------------------------------------
try:
    import cPickle as pickle
except ImportError:
    import pickle

# ------------------------------------------------------------------
# StringIO -- prefer the C implementation when available
# ------------------------------------------------------------------
try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from StringIO import StringIO as BytesIO

from StringIO import StringIO


def ensure_bytes(value, encoding="utf-8"):
    """Coerce *value* to a byte string."""
    if isinstance(value, unicode):
        return value.encode(encoding)
    if isinstance(value, str):
        return value
    return str(value)


def ensure_text(value, encoding="utf-8"):
    """Coerce *value* to a unicode string."""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        return value.decode(encoding)
    return unicode(value)
