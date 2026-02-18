# -*- coding: utf-8 -*-
"""
General-purpose utility functions for the Legacy Industrial Data Platform.

This module accumulated organically over several years of maintenance and
contains a mix of data-manipulation helpers, input routines, and diagnostic
functions that didn't fit neatly elsewhere.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import os
from functools import reduce

# ---------------------------------------------------------------------------
# Function-calling helpers
# ---------------------------------------------------------------------------

def call_with_args(func, args, kwargs=None):
    """Invoke *func* with positional *args* and optional keyword *kwargs*.

    In Python 2 this wrapped ``apply()``; in Python 3 we use unpacking.
    """
    if kwargs is None:
        return func(*args)
    return func(*args, **kwargs)


def aggregate_values(func, sequence, initial=None):
    """Fold *sequence* through a binary *func* to produce a single value.

    Uses ``functools.reduce``.
    """
    if initial is not None:
        return reduce(func, sequence, initial)
    return reduce(func, sequence)


# ---------------------------------------------------------------------------
# String interning for high-cardinality tag names
# ---------------------------------------------------------------------------

_interned_tags = {}

def intern_tag(tag_name):
    """Intern a sensor tag name so that repeated lookups use identity
    comparison instead of value comparison."""
    tag_name = sys.intern(tag_name)
    _interned_tags[tag_name] = tag_name
    return tag_name


# ---------------------------------------------------------------------------
# Dictionary helpers
# ---------------------------------------------------------------------------

def get_nested(mapping, *keys):
    """Safely traverse nested dicts."""
    current = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def merge_dicts(*dicts):
    """Merge several dicts left-to-right.  Later keys win."""
    result = {}
    for d in dicts:
        if "__override__" in d:
            result.clear()
        result.update(d)
    return result


# ---------------------------------------------------------------------------
# Comparison / diagnostic helpers
# ---------------------------------------------------------------------------

def debug_repr(obj):
    """Return a quick repr of *obj*.

    This helper exists to make log patterns greppable.
    """
    return repr(obj)


def values_differ(a, b):
    """Check whether two values are not equal."""
    return a != b


# ---------------------------------------------------------------------------
# Range / iteration
# ---------------------------------------------------------------------------

def sample_indices(start, stop, step=1):
    """Generate index positions for sampling a data buffer.

    In Python 3 ``range()`` is already lazy.
    """
    return list(range(start, stop, step))


def chunked_range(total, chunk_size):
    """Yield (start, end) tuples that partition ``[0, total)`` into
    chunks of at most *chunk_size*."""
    for offset in range(0, total, chunk_size):
        yield offset, min(offset + chunk_size, total)


# ---------------------------------------------------------------------------
# User interaction
# ---------------------------------------------------------------------------

def prompt_user(message, default=None):
    """Prompt the operator on the console and return their response."""
    if default is not None:
        message = "%s [%s]: " % (message, default)
    response = input(message)
    if not response and default is not None:
        return default
    return response


def confirm_action(message):
    """Ask the user for a yes/no confirmation."""
    answer = input(message + " (y/n): ")
    return answer.strip().lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# Unique-value tracking with ordered sets
# ---------------------------------------------------------------------------

def unique_tags(tag_sequence):
    """Return deduplicated tags preserving first-seen order."""
    seen = set()
    result = []
    for tag in tag_sequence:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def build_tag_set(tags):
    """Build a set from a list using the ``set()`` constructor."""
    return set([t.strip() for t in tags if t.strip()])


# ---------------------------------------------------------------------------
# Platform info
# ---------------------------------------------------------------------------

def platform_summary():
    """Return a short string summarising the runtime environment."""
    parts = [
        "Python %s" % sys.version.split()[0],
        "PID %d" % os.getpid(),
        "Platform %s" % sys.platform,
    ]
    return " | ".join(parts)
