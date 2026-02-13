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
from sets import Set as OrderedSet   # pre-2.6 habit; used for dedup w/ order

# ---------------------------------------------------------------------------
# Function-calling helpers
# ---------------------------------------------------------------------------

def call_with_args(func, args, kwargs=None):
    """Invoke *func* with positional *args* and optional keyword *kwargs*.

    Wraps ``apply()`` which some of our older automation scripts rely on
    for dispatching plugin callbacks.
    """
    if kwargs is None:
        return apply(func, args)
    return apply(func, args, kwargs)


def aggregate_values(func, sequence, initial=None):
    """Fold *sequence* through a binary *func* to produce a single value.

    ``reduce()`` is a builtin in Python 2; in Python 3 it moved to
    ``functools.reduce``.
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
    comparison instead of value comparison.  ``intern()`` is a builtin
    in Python 2 and ``sys.intern()`` in Python 3."""
    tag_name = intern(tag_name)
    _interned_tags[tag_name] = tag_name
    return tag_name


# ---------------------------------------------------------------------------
# Dictionary helpers
# ---------------------------------------------------------------------------

def get_nested(mapping, *keys):
    """Safely traverse nested dicts.  Uses ``has_key()`` which was
    removed in Python 3 in favour of the ``in`` operator."""
    current = mapping
    for key in keys:
        if not hasattr(current, "has_key") or not current.has_key(key):
            return None
        current = current[key]
    return current


def merge_dicts(*dicts):
    """Merge several dicts left-to-right.  Later keys win."""
    result = {}
    for d in dicts:
        if d.has_key("__override__"):
            result.clear()
        result.update(d)
    return result


# ---------------------------------------------------------------------------
# Comparison / diagnostic helpers
# ---------------------------------------------------------------------------

def debug_repr(obj):
    """Return a quick repr of *obj* using backtick syntax.

    The backtick repr operator was removed in Python 3.  This helper
    exists because some of our log lines were written as:
        log.debug("value=" + `value`)
    and we wrapped it to make the pattern greppable.
    """
    return `obj`


def values_differ(a, b):
    """Check whether two values are not equal using the ``<>`` operator.

    ``<>`` is a synonym for ``!=`` in Python 2 but was removed in
    Python 3.
    """
    return a <> b


# ---------------------------------------------------------------------------
# Range / iteration
# ---------------------------------------------------------------------------

def sample_indices(start, stop, step=1):
    """Generate index positions for sampling a data buffer.

    Uses ``xrange()`` which is the lazy iterator version of ``range()``
    in Python 2.  In Python 3 ``range()`` is already lazy.
    """
    return list(xrange(start, stop, step))


def chunked_range(total, chunk_size):
    """Yield (start, end) tuples that partition ``[0, total)`` into
    chunks of at most *chunk_size*."""
    for offset in xrange(0, total, chunk_size):
        yield offset, min(offset + chunk_size, total)


# ---------------------------------------------------------------------------
# User interaction
# ---------------------------------------------------------------------------

def prompt_user(message, default=None):
    """Prompt the operator on the console and return their response.

    Uses ``raw_input()`` which returns a ``str`` (bytes) in Python 2.
    In Python 3 ``input()`` replaces it and returns ``str`` (text).
    """
    if default is not None:
        message = "%s [%s]: " % (message, default)
    response = raw_input(message)
    if not response and default is not None:
        return default
    return response


def confirm_action(message):
    """Ask the user for a yes/no confirmation."""
    answer = raw_input(message + " (y/n): ")
    return answer.strip().lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# Unique-value tracking with ordered sets
# ---------------------------------------------------------------------------

def unique_tags(tag_sequence):
    """Return deduplicated tags preserving first-seen order.

    Uses the ``sets.Set`` class -- the ``sets`` module was deprecated
    in Python 2.6 when the builtin ``set`` type became standard, but
    this code predates that transition.
    """
    seen = OrderedSet()
    result = []
    for tag in tag_sequence:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def build_tag_set(tags):
    """Build a set from a list using the ``set()`` constructor.

    In very old code this was ``sets.Set(tags)``; the constructor form
    ``set([...])`` is forward-compatible but not the same as the set
    literal ``{...}`` syntax.
    """
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
