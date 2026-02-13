# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/cache.py

Captures pre-migration behavior of:
- CacheEntry with long() timestamps and sha.new() fingerprinting
- LRUCache with md5.new() bucket hashing and dict.iteritems()
- CacheManager with hashlib.md5(str) and cPickle disk persistence
- Py2-specific: long literals, md5 module, sha module, cPickle,
  integer division /, dict.iteritems(), StandardError
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.storage.cache import (
    CacheEntry, LRUCache, CacheManager,
    DEFAULT_TTL, MAX_ENTRIES, NUM_BUCKETS,
)


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------

class TestCacheEntry:
    """Characterize cache entry with TTL and fingerprinting."""

    @pytest.mark.py2_behavior
    def test_construction_uses_long(self):
        """Captures: created_at and last_access use long(time.time()).
        long() removed in Py3."""
        entry = CacheEntry("key1", "value1", ttl=60)
        assert entry.key == "key1"
        assert entry.value == "value1"
        assert entry.ttl == 60
        assert isinstance(entry.created_at, (int, long))
        assert isinstance(entry.access_count, (int, long))

    def test_is_expired_false_when_fresh(self):
        """Captures: freshly created entry is not expired."""
        entry = CacheEntry("k", "v", ttl=3600)
        assert entry.is_expired() is False

    def test_is_expired_true_when_old(self):
        """Captures: entry with ttl=0 is immediately expired."""
        entry = CacheEntry("k", "v", ttl=0)
        # created_at is set to long(time.time()), ttl=0 means always expired
        # There might be a race, but ttl=0 should be expired on next check
        time.sleep(0.01)
        assert entry.is_expired() is True

    @pytest.mark.py2_behavior
    def test_touch_updates_access(self):
        """Captures: touch increments access_count by 1L (long literal)."""
        entry = CacheEntry("k", "v")
        initial = entry.access_count
        entry.touch()
        assert entry.access_count == initial + 1

    @pytest.mark.py2_behavior
    def test_fingerprint_uses_sha(self):
        """Captures: fingerprint via sha.new(cPickle.dumps(value, 2)).hexdigest().
        sha module removed in Py3; use hashlib.sha1()."""
        entry = CacheEntry("k", {"sensor": "TEMP-001"})
        assert entry.fingerprint is not None
        assert isinstance(entry.fingerprint, str)
        # SHA-1 hexdigest is 40 chars
        assert len(entry.fingerprint) == 40

    def test_fingerprint_none_for_unpicklable(self):
        """Captures: unpicklable value produces fingerprint=None."""
        entry = CacheEntry("k", lambda x: x)
        assert entry.fingerprint is None


# ---------------------------------------------------------------------------
# LRUCache
# ---------------------------------------------------------------------------

class TestLRUCache:
    """Characterize the LRU cache with bucket hashing."""

    def test_put_and_get(self):
        """Captures: basic put/get round-trip."""
        cache = LRUCache(max_size=100)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_returns_none(self):
        """Captures: missing key returns None and increments misses."""
        cache = LRUCache()
        assert cache.get("missing") is None

    def test_invalidate(self):
        """Captures: invalidate removes entry."""
        cache = LRUCache()
        cache.put("k", "v")
        cache.invalidate("k")
        assert cache.get("k") is None

    def test_expired_entry_returns_none(self):
        """Captures: expired entries are auto-removed on get."""
        cache = LRUCache()
        cache.put("k", "v", ttl=0)
        time.sleep(0.01)
        assert cache.get("k") is None

    def test_eviction_when_full(self):
        """Captures: putting beyond max_size triggers LRU eviction."""
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        time.sleep(0.01)
        cache.put("b", 2)
        time.sleep(0.01)
        cache.put("c", 3)
        cache.put("d", 4)  # should evict "a" (oldest)
        assert cache.get("a") is None
        assert cache.get("d") == 4

    @pytest.mark.py2_behavior
    def test_bucket_for_key_uses_md5_new(self):
        """Captures: _bucket_for_key uses md5.new(key) (removed in Py3).
        Also uses integer division / instead of //."""
        cache = LRUCache(num_buckets=64)
        bucket = cache._bucket_for_key("test_key")
        assert 0 <= bucket < 64

    @pytest.mark.py2_behavior
    def test_stats_uses_long_counters(self):
        """Captures: stats counters initialized with 0L (long literals)."""
        cache = LRUCache()
        cache.put("k", "v")
        cache.get("k")
        cache.get("missing")
        stats = cache.stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert "hit_rate_pct" in stats


# ---------------------------------------------------------------------------
# CacheManager
# ---------------------------------------------------------------------------

class TestCacheManager:
    """Characterize the high-level cache manager with disk persistence."""

    @pytest.fixture
    def manager(self, tmp_path):
        return CacheManager(cache_dir=str(tmp_path), max_size=100, default_ttl=300)

    @pytest.fixture
    def memory_manager(self):
        """Manager without disk persistence."""
        return CacheManager(max_size=100, default_ttl=300)

    def test_set_and_get(self, memory_manager):
        """Captures: basic set/get through CacheManager."""
        memory_manager.set("sensor_config", {"id": "S001"})
        result = memory_manager.get("sensor_config")
        assert result == {"id": "S001"}

    def test_get_missing_returns_none(self, memory_manager):
        """Captures: missing key returns None."""
        assert memory_manager.get("nonexistent") is None

    def test_invalidate(self, memory_manager):
        """Captures: invalidate removes from memory cache."""
        memory_manager.set("k", "v")
        memory_manager.invalidate("k")
        assert memory_manager.get("k") is None

    @pytest.mark.py2_behavior
    def test_hash_key_uses_hashlib_md5(self, memory_manager):
        """Captures: _hash_key passes raw_key (str bytes in Py2) to hashlib.md5().
        In Py3, hashlib.md5() requires bytes, not str."""
        hashed = CacheManager._hash_key("test_key")
        assert isinstance(hashed, str)
        assert len(hashed) == 32  # md5 hex digest

    def test_warm_populates_cache(self, memory_manager):
        """Captures: warm pre-populates with key-value pairs."""
        pairs = [("k1", "v1"), ("k2", "v2"), ("k3", "v3")]
        memory_manager.warm(pairs)
        assert memory_manager.get("k1") == "v1"
        assert memory_manager.get("k3") == "v3"

    def test_stats(self, memory_manager):
        """Captures: stats returns dict with size, hits, misses etc."""
        memory_manager.set("k", "v")
        memory_manager.get("k")
        stats = memory_manager.stats()
        assert "size" in stats
        assert "hits" in stats

    @pytest.mark.py2_behavior
    def test_flush_to_disk_uses_cpickle(self, manager):
        """Captures: flush_to_disk serializes with cPickle.dumps(obj, 2).
        cPickle removed in Py3; use pickle."""
        manager.set("persist_key", {"data": [1, 2, 3]})
        manager.flush_to_disk()
        # Check that a .cache file was written
        cache_files = [f for f in os.listdir(manager._cache_dir) if f.endswith(".cache")]
        assert len(cache_files) >= 1

    @pytest.mark.py2_behavior
    def test_disk_round_trip(self, manager):
        """Captures: cPickle serialization round-trip via disk persistence."""
        manager.set("rt_key", {"sensor": "TEMP", "cal": [1.0, 0.5]})
        manager.flush_to_disk()
        # Create a new manager pointing at the same directory
        manager2 = CacheManager(cache_dir=manager._cache_dir, default_ttl=300)
        result = manager2.get("rt_key")
        assert result == {"sensor": "TEMP", "cal": [1.0, 0.5]}

    def test_purge_expired(self, memory_manager):
        """Captures: purge_expired removes entries past their TTL."""
        memory_manager._cache.put(
            CacheManager._hash_key("old"),
            "old_value",
            ttl=0,
        )
        time.sleep(0.01)
        purged = memory_manager.purge_expired()
        assert purged >= 1


# ---------------------------------------------------------------------------
# Encoding boundary tests
# ---------------------------------------------------------------------------

class TestCacheEncodingBoundaries:
    """Test encoding edge cases in cache operations."""

    @pytest.mark.py2_behavior
    def test_hash_key_with_unicode(self):
        """Captures: hashlib.md5 on unicode string. Py2 auto-encodes to ASCII;
        Py3 requires explicit .encode()."""
        # In Py2 with unicode_literals, this is a unicode string
        hashed = CacheManager._hash_key("caf\u00e9")
        assert len(hashed) == 32

    @pytest.mark.py2_behavior
    def test_cache_unicode_value(self):
        """Captures: caching unicode values; sha fingerprint handles them."""
        mgr = CacheManager(max_size=10)
        mgr.set(u"unicode_key", {u"label": u"caf\u00e9"})
        result = mgr.get(u"unicode_key")
        assert result[u"label"] == u"caf\u00e9"

    @pytest.mark.py2_behavior
    def test_cache_binary_value(self):
        """Captures: caching binary data; cPickle serializes bytes."""
        mgr = CacheManager(max_size=10)
        mgr.set("binary_key", b"\x00\x7F\x80\xFF")
        result = mgr.get("binary_key")
        assert result == b"\x00\x7F\x80\xFF"
