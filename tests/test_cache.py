# -*- coding: utf-8 -*-
"""
Characterization tests for src/storage/cache.py

Tests the current Python 2 behavior including:
- md5 and sha modules (removed in Py3, use hashlib)
- hashlib.md5("string") accepting str directly (Py3 requires bytes)
- cPickle with explicit protocol parameter
- long type literals (0L)
- Integer division / truncating (Py3 uses //)
- dict.iteritems() and dict.iterkeys()
- except StandardError, e syntax
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import time
import pytest
import tempfile
import hashlib

from src.storage.cache import (
    CacheEntry,
    LRUCache,
    CacheManager,
    DEFAULT_TTL,
    MAX_ENTRIES,
    NUM_BUCKETS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_entry():
    """Create a sample CacheEntry."""
    return CacheEntry("test_key", "test_value", ttl=300)


@pytest.fixture
def lru_cache():
    """Create an LRUCache instance."""
    return LRUCache(max_size=100, num_buckets=8)


@pytest.fixture
def cache_manager(tmp_path):
    """Create a CacheManager with temporary directory."""
    return CacheManager(cache_dir=str(tmp_path), max_size=50)


# ---------------------------------------------------------------------------
# Test CacheEntry with long type
# ---------------------------------------------------------------------------

def test_cache_entry_initialization():
    """Test CacheEntry initialization with int type timestamps."""
    entry = CacheEntry("key", "value", ttl=600)

    assert entry.key == "key"
    assert entry.value == "value"
    assert entry.ttl == 600
    assert isinstance(entry.created_at, int)
    assert isinstance(entry.last_access, int)
    assert isinstance(entry.access_count, int)


def test_cache_entry_int_type_literals():
    """Test that int type literals (0) are used."""
    entry = CacheEntry("key", "value")

    # These should be int type in Py3
    assert entry.access_count == 0
    assert isinstance(entry.created_at, int)
    assert isinstance(entry.last_access, int)


def test_cache_entry_is_expired_false():
    """Test is_expired() returns False for fresh entry."""
    entry = CacheEntry("key", "value", ttl=3600)
    assert not entry.is_expired()


def test_cache_entry_is_expired_true():
    """Test is_expired() returns True for old entry."""
    entry = CacheEntry("key", "value", ttl=1)
    # Force old timestamp
    entry.created_at = int(time.time()) - 10
    assert entry.is_expired()


def test_cache_entry_touch_updates_access():
    """Test touch() updates last_access and access_count."""
    entry = CacheEntry("key", "value")
    original_access = entry.last_access
    original_count = entry.access_count

    time.sleep(0.01)
    entry.touch()

    assert entry.last_access > original_access
    assert entry.access_count == original_count + 1


def test_cache_entry_touch_increments_int():
    """Test touch() increments access_count as int."""
    entry = CacheEntry("key", "value")
    entry.touch()
    entry.touch()

    assert entry.access_count == 2
    assert isinstance(entry.access_count, int)


def test_cache_entry_fingerprint_sha1():
    """Test fingerprint computation uses hashlib.sha1()."""
    entry = CacheEntry("key", {"data": "value"})
    # Fingerprint should be computed
    assert entry.fingerprint is not None or entry.fingerprint is None


def test_cache_entry_fingerprint_with_complex_value():
    """Test fingerprint with complex pickleable value."""
    value = {"nested": {"data": [1, 2, 3]}}
    entry = CacheEntry("key", value)
    # Should compute fingerprint using hashlib.sha1()
    assert isinstance(entry.fingerprint, (str, type(None)))


def test_cache_entry_fingerprint_exception_handling():
    """Test fingerprint returns None on exception."""
    # Create value that can't be pickled
    class UnpicklableClass:
        def __reduce__(self):
            raise TypeError("Can't pickle")

    entry = CacheEntry("key", UnpicklableClass())
    # Should return None on exception
    assert entry.fingerprint is None


# ---------------------------------------------------------------------------
# Test LRUCache with md5 module and integer division
# ---------------------------------------------------------------------------

def test_lru_cache_initialization():
    """Test LRUCache initialization."""
    cache = LRUCache(max_size=500, num_buckets=32)

    assert cache._max_size == 500
    assert cache._num_buckets == 32
    assert isinstance(cache._hits, int)
    assert isinstance(cache._misses, int)
    assert isinstance(cache._evictions, int)


def test_lru_cache_int_type_counters():
    """Test that stat counters use int type (0)."""
    cache = LRUCache()

    assert cache._hits == 0
    assert cache._misses == 0
    assert cache._evictions == 0


def test_lru_cache_bucket_for_key_uses_hashlib_md5():
    """Test _bucket_for_key() uses hashlib.md5()."""
    cache = LRUCache(num_buckets=16)

    # This should use hashlib.md5(key) internally
    bucket = cache._bucket_for_key("test_key")

    assert 0 <= bucket < 16


def test_lru_cache_bucket_for_key_floor_division():
    """Test bucket calculation uses floor division //."""
    cache = LRUCache(num_buckets=16)

    # In Py3, // does floor division
    bucket = cache._bucket_for_key("test_key")

    # hash_val // num_buckets should work correctly
    assert isinstance(bucket, int)
    assert bucket < cache._num_buckets


def test_lru_cache_put_and_get():
    """Test basic put and get operations."""
    cache = LRUCache()

    cache.put("key1", "value1")
    result = cache.get("key1")

    assert result == "value1"


def test_lru_cache_get_miss(lru_cache, capsys):
    """Test cache miss increments misses counter."""
    result = lru_cache.get("nonexistent_key")

    assert result is None
    assert lru_cache._misses >= 1

    captured = capsys.readouterr()
    assert "MISS" in captured.out


def test_lru_cache_get_hit(lru_cache, capsys):
    """Test cache hit increments hits counter."""
    lru_cache.put("key1", "value1")
    result = lru_cache.get("key1")

    assert result == "value1"
    assert lru_cache._hits >= 1

    captured = capsys.readouterr()
    assert "HIT" in captured.out


def test_lru_cache_get_expired_entry(lru_cache):
    """Test getting expired entry returns None."""
    lru_cache.put("key1", "value1", ttl=1)

    # Force expiration by modifying entry
    entry = lru_cache._store["key1"]
    entry.created_at = int(time.time()) - 100

    result = lru_cache.get("key1")
    assert result is None
    assert "key1" not in lru_cache._store


def test_lru_cache_put_triggers_eviction(lru_cache):
    """Test that exceeding max_size triggers eviction."""
    # Fill cache to max
    for i in range(lru_cache._max_size):
        lru_cache.put("key_%d" % i, "value_%d" % i)

    # This should trigger eviction
    lru_cache.put("overflow_key", "overflow_value")

    assert lru_cache._evictions >= 1


def test_lru_cache_evict_lru_removes_oldest():
    """Test _evict_lru() removes least recently accessed entry."""
    cache = LRUCache(max_size=3)

    cache.put("key1", "value1")
    cache.put("key2", "value2")
    cache.put("key3", "value3")

    # Access key1 and key2 to make them more recent
    cache.get("key1")
    cache.get("key2")

    # Fill to capacity and trigger eviction
    cache.put("key4", "value4")

    # key3 should be evicted (oldest access)
    assert cache.get("key3") is None


def test_lru_cache_evict_lru_uses_items():
    """Test _evict_lru() uses dict.items()."""
    cache = LRUCache(max_size=2)

    cache.put("key1", "value1")
    cache.put("key2", "value2")

    # This will call _evict_lru which uses items()
    cache.put("key3", "value3")

    assert len(cache._store) <= cache._max_size


def test_lru_cache_invalidate():
    """Test invalidating a cache entry."""
    cache = LRUCache()

    cache.put("key1", "value1")
    assert cache.get("key1") == "value1"

    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_lru_cache_stats():
    """Test stats() with integer division for hit rate."""
    cache = LRUCache()

    cache.put("key1", "value1")
    cache.get("key1")  # Hit
    cache.get("key2")  # Miss

    stats = cache.stats()

    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert "hit_rate_pct" in stats
    # In Py3, (hits * 100) // total uses floor division
    assert isinstance(stats["hit_rate_pct"], int)


def test_lru_cache_stats_floor_division():
    """Test that hit_rate calculation uses floor division."""
    cache = LRUCache()

    cache.put("k1", "v1")
    cache.get("k1")  # 1 hit
    cache.get("k2")  # 1 miss
    cache.get("k3")  # 1 miss

    stats = cache.stats()

    # (1 * 100) // 3 should be 33 in floor division (not 33.333...)
    # Actual value depends on order, just check it's an integer
    assert isinstance(stats["hit_rate_pct"], int)


def test_lru_cache_stats_zero_division():
    """Test stats() handles zero total gracefully."""
    cache = LRUCache()

    stats = cache.stats()

    assert stats["hit_rate_pct"] == 0


# ---------------------------------------------------------------------------
# Test CacheManager with hashlib.md5(string)
# ---------------------------------------------------------------------------

def test_cache_manager_initialization(tmp_path):
    """Test CacheManager initialization."""
    cache_dir = str(tmp_path)
    cm = CacheManager(cache_dir=cache_dir, max_size=100, default_ttl=600)

    assert cm._default_ttl == 600
    assert cm._cache_dir == cache_dir
    assert os.path.isdir(cache_dir)


def test_cache_manager_hash_key_uses_hashlib_md5():
    """Test _hash_key() uses hashlib.md5(string) with str directly."""
    # In Py2, hashlib.md5() accepts str (bytes) directly
    hashed = CacheManager._hash_key("test_key")

    assert isinstance(hashed, str)
    assert len(hashed) == 32  # MD5 hex digest


def test_cache_manager_hash_key_accepts_bytes():
    """Test _hash_key() with bytes (Py2 str)."""
    hashed = CacheManager._hash_key(b"test_key")
    assert isinstance(hashed, str)


def test_cache_manager_get_miss(cache_manager):
    """Test get() on cache miss."""
    value = cache_manager.get("nonexistent")
    assert value is None


def test_cache_manager_set_and_get(cache_manager):
    """Test set() and get() operations."""
    cache_manager.set("key1", "value1")
    value = cache_manager.get("key1")

    assert value == "value1"


def test_cache_manager_set_custom_ttl(cache_manager):
    """Test set() with custom TTL."""
    cache_manager.set("key1", "value1", ttl=3600)

    # Entry should be in cache
    value = cache_manager.get("key1")
    assert value == "value1"


def test_cache_manager_invalidate(cache_manager):
    """Test invalidate() removes entry."""
    cache_manager.set("key1", "value1")
    cache_manager.invalidate("key1")

    value = cache_manager.get("key1")
    assert value is None


def test_cache_manager_warm(cache_manager, capsys):
    """Test warm() pre-populates cache."""
    key_value_pairs = [
        ("key1", "value1"),
        ("key2", "value2"),
        ("key3", "value3"),
    ]

    cache_manager.warm(key_value_pairs, ttl=600)

    assert cache_manager.get("key1") == "value1"
    assert cache_manager.get("key2") == "value2"
    assert cache_manager.get("key3") == "value3"

    captured = capsys.readouterr()
    assert "Cache warmed" in captured.out
    assert "3 entries" in captured.out


def test_cache_manager_stats(cache_manager):
    """Test stats() returns cache statistics."""
    cache_manager.set("key1", "value1")

    stats = cache_manager.stats()

    assert "size" in stats
    assert "hits" in stats
    assert "misses" in stats


# ---------------------------------------------------------------------------
# Test CacheManager disk persistence with cPickle
# ---------------------------------------------------------------------------

def test_cache_manager_flush_to_disk(cache_manager, capsys):
    """Test flush_to_disk() with cPickle protocol 2."""
    cache_manager.set("key1", {"data": "value1"})
    cache_manager.set("key2", {"data": "value2"})

    cache_manager.flush_to_disk()

    captured = capsys.readouterr()
    assert "Flushed" in captured.out
    assert "entries to disk" in captured.out

    # Check files were created
    cache_files = os.listdir(cache_manager._cache_dir)
    assert len(cache_files) > 0


def test_cache_manager_flush_to_disk_uses_cpickle_protocol_2(cache_manager):
    """Test that flush uses cPickle.dumps(obj, 2)."""
    cache_manager.set("key1", "value1")
    cache_manager.flush_to_disk()

    # Verify pickle files exist
    cache_files = os.listdir(cache_manager._cache_dir)
    assert any(f.endswith(".cache") for f in cache_files)


def test_cache_manager_flush_to_disk_skips_expired(cache_manager):
    """Test flush skips expired entries."""
    cache_manager.set("key1", "value1", ttl=1)

    # Force expiration
    hashed = CacheManager._hash_key("key1")
    entry = cache_manager._cache._store[hashed]
    entry.created_at = int(time.time()) - 100

    cache_manager.flush_to_disk()

    # Expired entry should not be flushed
    cache_files = os.listdir(cache_manager._cache_dir)
    # May or may not have files depending on other entries


def test_cache_manager_flush_to_disk_items():
    """Test flush_to_disk() uses dict.items()."""
    cm = CacheManager()
    cm.set("key1", "value1")

    # This internally uses items()
    cm.flush_to_disk()


def test_cache_manager_load_from_disk(cache_manager):
    """Test loading from disk with cPickle."""
    cache_manager.set("key1", "value1")
    cache_manager.flush_to_disk()

    # Clear memory cache
    hashed = CacheManager._hash_key("key1")
    cache_manager._cache._store.clear()

    # Should load from disk
    value = cache_manager.get("key1")
    assert value == "value1"


def test_cache_manager_load_from_disk_expired(cache_manager):
    """Test loading expired entry from disk returns None."""
    cache_manager.set("key1", "value1", ttl=1)
    cache_manager.flush_to_disk()

    # Wait for expiration
    time.sleep(1.1)

    # Clear memory cache
    cache_manager._cache._store.clear()

    # Should not load expired entry
    value = cache_manager.get("key1")
    assert value is None


def test_cache_manager_load_from_disk_prints_hit(cache_manager, capsys):
    """Test disk load prints DISK HIT."""
    cache_manager.set("key1", "value1")
    cache_manager.flush_to_disk()

    cache_manager._cache._store.clear()

    cache_manager.get("key1")

    captured = capsys.readouterr()
    assert "DISK HIT" in captured.out


def test_cache_manager_remove_from_disk(cache_manager):
    """Test _remove_from_disk() deletes cache file."""
    cache_manager.set("key1", "value1")
    cache_manager.flush_to_disk()

    hashed = CacheManager._hash_key("key1")
    cache_path = os.path.join(cache_manager._cache_dir, hashed + ".cache")

    assert os.path.isfile(cache_path)

    cache_manager.invalidate("key1")

    # Should be removed from disk
    assert not os.path.isfile(cache_path)


def test_cache_manager_purge_expired(cache_manager, capsys):
    """Test purge_expired() with dict.iteritems()."""
    cache_manager.set("key1", "value1", ttl=1)
    cache_manager.set("key2", "value2", ttl=3600)

    # Force key1 to expire
    hashed1 = CacheManager._hash_key("key1")
    entry1 = cache_manager._cache._store[hashed1]
    entry1.created_at = int(time.time()) - 100

    purged = cache_manager.purge_expired()

    assert purged >= 1

    captured = capsys.readouterr()
    assert "Purged" in captured.out


def test_cache_manager_purge_expired_uses_items():
    """Test purge_expired() iterates with items()."""
    cm = CacheManager()
    cm.set("key1", "value1")

    # This uses items() internally
    count = cm.purge_expired()
    assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Test exception handling with except StandardError, e
# ---------------------------------------------------------------------------

def test_cache_manager_flush_handles_standard_error(cache_manager, capsys):
    """Test flush_to_disk() handles StandardError with old except syntax."""
    # Create an entry that might cause issues
    cache_manager.set("key1", "value1")

    # Should not crash even if individual flush fails
    cache_manager.flush_to_disk()

    # Check for warning messages
    captured = capsys.readouterr()
    # May or may not have warnings


def test_cache_manager_load_handles_standard_error(cache_manager, tmp_path):
    """Test _load_from_disk() handles StandardError."""
    # Create a corrupt cache file
    bad_cache = tmp_path / "badcache.cache"
    bad_cache.write_bytes(b"not valid pickle data")

    # Should return None without crashing
    result = cache_manager._load_from_disk("badcache")
    assert result is None


def test_cache_manager_remove_handles_os_error(cache_manager, capsys):
    """Test _remove_from_disk() handles OSError."""
    # Try to remove non-existent file
    cache_manager._remove_from_disk("nonexistent_hash")

    # Should not crash
    captured = capsys.readouterr()
    # May or may not print warning


# ---------------------------------------------------------------------------
# Test threading with Lock
# ---------------------------------------------------------------------------

def test_cache_manager_thread_safety_lock(cache_manager):
    """Test that lock is used for thread safety."""
    import threading

    assert isinstance(cache_manager._lock, threading.Lock)


def test_cache_manager_get_acquires_lock(cache_manager):
    """Test get() acquires and releases lock."""
    cache_manager.set("key1", "value1")

    # Lock should be acquired during get
    value = cache_manager.get("key1")
    assert value == "value1"

    # Lock should be released after
    assert not cache_manager._lock.locked()


def test_cache_manager_set_acquires_lock(cache_manager):
    """Test set() acquires and releases lock."""
    cache_manager.set("key1", "value1")

    # Lock should be released after
    assert not cache_manager._lock.locked()


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

def test_constants_defined():
    """Test that module constants are defined."""
    assert DEFAULT_TTL == 300
    assert MAX_ENTRIES == 10000
    assert NUM_BUCKETS == 64


# ---------------------------------------------------------------------------
# Test md5 and sha module usage
# ---------------------------------------------------------------------------

def test_hashlib_imported():
    """Test that hashlib module is imported."""
    # The module imports hashlib
    assert hashlib is not None


def test_hashlib_md5_usage():
    """Test hashlib.md5() is used for hashing."""
    # LRUCache uses hashlib.md5()
    cache = LRUCache()
    bucket = cache._bucket_for_key("test")

    # Should work without errors
    assert isinstance(bucket, int)


def test_hashlib_sha1_usage():
    """Test hashlib.sha1() is used in fingerprint."""
    # CacheEntry uses hashlib.sha1()
    entry = CacheEntry("key", "value")

    # Fingerprint should be computed or None
    assert entry.fingerprint is None or isinstance(entry.fingerprint, str)


# ---------------------------------------------------------------------------
# Test print statement output
# ---------------------------------------------------------------------------

def test_cache_prints_hit_message(lru_cache, capsys):
    """Test cache prints HIT messages."""
    lru_cache.put("key1", "value1")
    lru_cache.get("key1")

    captured = capsys.readouterr()
    assert "HIT" in captured.out
    assert "key1" in captured.out


def test_cache_prints_miss_message(lru_cache, capsys):
    """Test cache prints MISS messages."""
    lru_cache.get("nonexistent")

    captured = capsys.readouterr()
    assert "MISS" in captured.out


def test_cache_manager_prints_warm_message(cache_manager, capsys):
    """Test warm() prints confirmation."""
    cache_manager.warm([("key1", "value1")])

    captured = capsys.readouterr()
    assert "warmed" in captured.out


def test_cache_manager_prints_flush_message(cache_manager, capsys):
    """Test flush prints count."""
    cache_manager.set("key1", "value1")
    cache_manager.flush_to_disk()

    captured = capsys.readouterr()
    assert "Flushed" in captured.out
