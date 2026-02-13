# -*- coding: utf-8 -*-
"""
Iterator and collection helpers for the Legacy Industrial Data Platform.

Sensor data arrives in high-volume streams that need to be batched,
windowed, grouped, and filtered before storage.  These helpers wrap
the standard library's itertools with domain-friendly APIs.

Most of the functions here use Python 2-specific iterator APIs
(``itertools.izip``, ``dict.iteritems``, generator ``.next()``
method) that changed in Python 3.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import itertools


# ---------------------------------------------------------------------------
# Batching -- split a sensor stream into fixed-size batches for bulk
# database inserts.
# ---------------------------------------------------------------------------

def batch_readings(iterable, batch_size):
    """Yield lists of at most *batch_size* items from *iterable*.

    Uses ``itertools.izip`` which was renamed to ``zip`` in Python 3
    (and the old ``zip`` was removed because it already returned a
    list in Py2).
    """
    iterator = iter(iterable)
    while True:
        # Take up to batch_size items by izip-ing with a range sentinel
        chunk = list(itertools.islice(iterator, batch_size))
        if not chunk:
            break
        yield chunk


def batch_with_index(iterable, batch_size):
    """Like ``batch_readings`` but yields ``(batch_index, batch)`` pairs.

    Uses ``itertools.izip`` to pair each batch with its ordinal.
    """
    batches = batch_readings(iterable, batch_size)
    for pair in zip(itertools.count(), batches):
        yield pair


# ---------------------------------------------------------------------------
# Sliding window -- used for rolling-average calculations on vibration
# and temperature channels.
# ---------------------------------------------------------------------------

def sliding_window(iterable, window_size):
    """Yield overlapping windows of *window_size* over *iterable*.

    Uses ``itertools.imap`` to transform the deque snapshots into tuples,
    and ``itertools.izip`` under the hood via the recipes pattern.
    """
    from collections import deque
    window = deque(maxlen=window_size)
    iterator = iter(iterable)

    # Fill the initial window
    for _ in range(window_size):
        window.append(next(iterator))
    yield tuple(window)

    # Slide forward one element at a time
    for item in iterator:
        window.append(item)
        yield tuple(window)


# ---------------------------------------------------------------------------
# Grouping -- group sensor readings by tag name for per-sensor
# aggregation passes.
# ---------------------------------------------------------------------------

def group_by_key(iterable, key_func):
    """Group items by a key function, returning a dict of lists.

    Uses ``itertools.ifilter`` to partition and ``dict.iteritems()``
    to traverse the result.
    """
    groups = {}
    for item in iterable:
        key = key_func(item)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)
    return groups


def iter_group_items(grouped_dict):
    """Iterate over (key, items) pairs from a grouped dict.

    Uses ``dict.iteritems()`` which returns a lazy iterator in
    Python 2; in Python 3 ``dict.items()`` is already lazy.
    """
    return grouped_dict.items()


def iter_group_keys(grouped_dict):
    """Iterate over the group keys only.

    Uses ``dict.iterkeys()`` -- lazy in Py2, replaced by
    ``dict.keys()`` in Py3.
    """
    return grouped_dict.keys()


# ---------------------------------------------------------------------------
# View-based set operations on dict keys (Python 2.7)
# ---------------------------------------------------------------------------

def common_tags(config_a, config_b):
    """Return tags present in both config dicts using ``dict.viewkeys()``
    set intersection.

    ``viewkeys()`` returns a set-like view in Python 2.7; in Python 3
    ``dict.keys()`` itself returns a view.
    """
    return config_a.keys() & config_b.keys()


def changed_values(old_config, new_config):
    """Return keys whose values differ between *old_config* and
    *new_config*.

    Uses ``dict.viewitems()`` for efficient symmetric-difference
    calculation.
    """
    return dict(
        (k, (old_config.get(k), new_config.get(k)))
        for k, _ in old_config.items() ^ new_config.items()
        if k in old_config and k in new_config
    )


def added_keys(old_config, new_config):
    """Return keys in *new_config* that are not in *old_config*."""
    return new_config.keys() - old_config.keys()


def config_values_snapshot(config_dict):
    """Return a frozenset of the config values for hashing/comparison.

    Uses ``dict.viewvalues()`` which has no direct Py3 equivalent
    (it maps to ``dict.values()``).
    """
    return list(config_dict.values())


# ---------------------------------------------------------------------------
# Transformation pipelines using imap / ifilter
# ---------------------------------------------------------------------------

def scale_readings(readings, factor):
    """Lazily multiply each reading value by *factor*.

    Uses ``itertools.imap`` which became the builtin ``map`` in
    Python 3.
    """
    return map(lambda r: r * factor, readings)


def filter_valid_readings(readings, min_quality=192):
    """Lazily drop readings below a quality threshold.

    Uses ``itertools.ifilter`` which became the builtin ``filter``
    in Python 3.
    """
    return filter(lambda r: r.quality >= min_quality, readings)


def zip_timestamps(readings_a, readings_b):
    """Pair up readings from two channels by position.

    Uses ``itertools.izip`` -- lazy in Py2, renamed to ``zip`` in Py3.
    """
    return zip(readings_a, readings_b)


# ---------------------------------------------------------------------------
# Eager list-producing wrappers (Py2 map/filter/zip return lists)
# ---------------------------------------------------------------------------

def extract_values(readings):
    """Return a list of decoded values from a sequence of readings.

    ``map()`` returns a list in Python 2; in Python 3 it returns a
    lazy iterator.
    """
    return list(map(lambda r: r.decoded_value, readings))


def good_readings(readings):
    """Return a list of readings with OPC quality >= 192.

    ``filter()`` returns a list in Python 2.
    """
    return list(filter(lambda r: r.quality >= 192, readings))


def paired_channels(channel_a, channel_b):
    """Zip two channel lists into a list of pairs.

    ``zip()`` returns a list in Python 2.
    """
    return list(zip(channel_a, channel_b))


# ---------------------------------------------------------------------------
# Generator consumption helpers
# ---------------------------------------------------------------------------

def take_next(iterator):
    """Pull the next value from *iterator* using the ``.next()`` method.

    In Python 3 the ``.next()`` method was removed; you must use
    ``next(iterator)`` instead.
    """
    return next(iterator)


def peek(iterator):
    """Peek at the next value without consuming the iterator.

    Returns ``(value, new_iterator)`` where *new_iterator* replays
    the peeked value.
    """
    value = next(iterator)
    return value, itertools.chain([value], iterator)


def drain(iterator, limit=None):
    """Consume up to *limit* items from *iterator* and return them as
    a list.  If *limit* is None, consume everything."""
    result = []
    count = 0
    for item in iterator:
        result.append(item)
        count += 1
        if limit is not None and count >= limit:
            break
    return result
