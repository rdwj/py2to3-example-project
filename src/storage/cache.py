# -*- coding: utf-8 -*-
"""
In-memory and disk cache for the Legacy Industrial Data Platform.

Reduces database load by caching sensor readings, statistics, and
configuration snapshots.  Uses ``hashlib`` for key hashing, ``pickle``
for serialisation, and integer division ``//`` for bucket assignment.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import time
import hashlib
import pickle
import threading

from src.core.exceptions import CacheError

DEFAULT_TTL = 300
MAX_ENTRIES = 10000
NUM_BUCKETS = 64
_EVICTION_BATCH = 128


class CacheEntry:
    """Cached value with TTL and access tracking for LRU eviction."""

    __slots__ = ("key", "value", "created_at", "last_access",
                 "ttl", "access_count", "fingerprint")

    def __init__(self, key, value, ttl=DEFAULT_TTL):
        self.key = key
        self.value = value
        self.created_at = int(time.time())
        self.last_access = int(time.time())
        self.ttl = ttl
        self.access_count = 0
        self.fingerprint = self._compute_fingerprint(value)

    def is_expired(self):
        return (int(time.time()) - self.created_at) > self.ttl

    def touch(self):
        self.last_access = int(time.time())
        self.access_count += 1

    @staticmethod
    def _compute_fingerprint(value):
        """SHA-1 fingerprint of the pickled value."""
        try:
            return hashlib.sha1(pickle.dumps(value, 2)).hexdigest()
        except Exception:
            return None


class LRUCache:
    """Fixed-size cache with LRU eviction.  Bucket assignment uses
    integer division ``//``."""

    def __init__(self, max_size=MAX_ENTRIES, num_buckets=NUM_BUCKETS):
        self._store = {}
        self._max_size = max_size
        self._num_buckets = num_buckets
        self._hits, self._misses, self._evictions = 0, 0, 0

    def _bucket_for_key(self, key):
        """Bucket via hashlib.md5.  Key is encoded to bytes for hashing."""
        hash_val = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
        bucket = hash_val // self._num_buckets
        return bucket % self._num_buckets

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            print("  [cache] MISS: %s" % key)
            return None
        if entry.is_expired():
            del self._store[key]
            self._misses += 1
            return None
        entry.touch()
        self._hits += 1
        print("  [cache] HIT: %s (bucket %d)" % (key, self._bucket_for_key(key)))
        return entry.value

    def put(self, key, value, ttl=DEFAULT_TTL):
        if len(self._store) >= self._max_size:
            self._evict_lru()
        self._store[key] = CacheEntry(key, value, ttl)

    def invalidate(self, key):
        if key in self._store:
            del self._store[key]

    def _evict_lru(self):
        if not self._store:
            return
        oldest_key, oldest_time, checked = None, int(time.time()) + 1, 0
        for k, entry in self._store.items():
            if entry.last_access < oldest_time:
                oldest_time = entry.last_access
                oldest_key = k
            checked += 1
            if checked >= _EVICTION_BATCH:
                break
        if oldest_key is not None:
            del self._store[oldest_key]
            self._evictions += 1

    def stats(self):
        total = self._hits + self._misses
        hit_rate = (self._hits * 100) / total if total > 0 else 0
        return {"size": len(self._store), "max_size": self._max_size,
                "hits": self._hits, "misses": self._misses,
                "evictions": self._evictions, "hit_rate_pct": hit_rate}


class CacheManager:
    """High-level cache with disk persistence.  Keys are encoded to
    bytes before passing to ``hashlib.md5()``."""

    def __init__(self, cache_dir=None, max_size=MAX_ENTRIES, default_ttl=DEFAULT_TTL):
        self._cache = LRUCache(max_size=max_size)
        self._default_ttl = default_ttl
        self._cache_dir = cache_dir
        self._lock = threading.Lock()
        if self._cache_dir and not os.path.isdir(self._cache_dir):
            os.makedirs(self._cache_dir)

    @staticmethod
    def _hash_key(raw_key):
        """Hash a string key.  Encode to bytes for hashlib compatibility."""
        if isinstance(raw_key, str):
            raw_key = raw_key.encode("utf-8")
        return hashlib.md5(raw_key).hexdigest()

    def get(self, key):
        hashed = self._hash_key(key)
        self._lock.acquire()
        try:
            value = self._cache.get(hashed)
            if value is not None:
                return value
        finally:
            self._lock.release()
        return self._load_from_disk(hashed)

    def set(self, key, value, ttl=None):
        hashed = self._hash_key(key)
        self._lock.acquire()
        try:
            self._cache.put(hashed, value, ttl or self._default_ttl)
        finally:
            self._lock.release()

    def invalidate(self, key):
        hashed = self._hash_key(key)
        self._lock.acquire()
        try:
            self._cache.invalidate(hashed)
        finally:
            self._lock.release()
        self._remove_from_disk(hashed)

    def warm(self, key_value_pairs, ttl=None):
        """Pre-populate at startup with sensor configs and calibration."""
        ttl = ttl or self._default_ttl
        loaded = 0
        for key, value in key_value_pairs:
            self.set(key, value, ttl)
            loaded += 1
        print("Cache warmed with %d entries (ttl=%d)" % (loaded, ttl))

    def stats(self):
        return self._cache.stats()

    def flush_to_disk(self):
        """Persist with pickle protocol 2."""
        if not self._cache_dir:
            return
        self._lock.acquire()
        try:
            entries = dict(self._cache._store)
        finally:
            self._lock.release()
        flushed = 0
        for hk, entry in entries.items():
            if entry.is_expired():
                continue
            path = os.path.join(self._cache_dir, hk + ".cache")
            try:
                data = pickle.dumps({"value": entry.value, "ttl": entry.ttl,
                                     "created_at": entry.created_at}, 2)
                with open(path, "wb") as f:
                    f.write(data)
                flushed += 1
            except Exception as e:
                print("WARNING: disk flush failed for %s: %s" % (hk, e))
        print("Flushed %d entries to disk" % flushed)

    def _load_from_disk(self, hashed_key):
        if not self._cache_dir:
            return None
        path = os.path.join(self._cache_dir, hashed_key + ".cache")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                rec = pickle.loads(f.read())
            age = int(time.time()) - rec["created_at"]
            if age > rec["ttl"]:
                os.remove(path)
                return None
            self._lock.acquire()
            try:
                self._cache.put(hashed_key, rec["value"], rec["ttl"] - age)
            finally:
                self._lock.release()
            print("  [cache] DISK HIT: %s" % hashed_key)
            return rec["value"]
        except Exception as e:
            print("WARNING: disk load failed for %s: %s" % (hashed_key, e))
            return None

    def _remove_from_disk(self, hashed_key):
        if not self._cache_dir:
            return
        path = os.path.join(self._cache_dir, hashed_key + ".cache")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError as e:
                print("WARNING: could not remove %s: %s" % (path, e))

    def purge_expired(self):
        self._lock.acquire()
        try:
            expired = [k for k, e in self._cache._store.items() if e.is_expired()]
            for key in expired:
                del self._cache._store[key]
        finally:
            self._lock.release()
        if expired:
            print("Purged %d expired cache entries" % len(expired))
        return len(expired)
