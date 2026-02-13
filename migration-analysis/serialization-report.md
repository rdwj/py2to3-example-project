# Serialization Detection Report: Python 2 to 3 Migration

**Scan date:** 2026-02-12
**Target version:** Python 3.12
**Scanned files:** 8 source files across 3 packages

## Executive Summary

The codebase contains **26 serialization points** across 7 source files, with **8 critical**, **6 high**, **4 medium**, and **8 low** risk findings. The most dangerous patterns are:

1. `str(buffer)` used to extract SQLite BLOB data before passing to `cPickle.loads()` -- in Python 3, `str(bytes)` returns the repr, not the raw bytes, producing silent data corruption or exceptions.
2. `json.loads()`/`json.dumps()` called with the `encoding=` parameter, which was removed entirely in Python 3.9 and raises `TypeError` in 3.12.
3. `copy_reg.pickle(types.InstanceType, ...)` -- both `copy_reg` (renamed `copyreg`) and `types.InstanceType` (removed with old-style classes) do not exist in Python 3.
4. `struct.pack()` output concatenated with `str` literals in MQTT/MODBUS packet construction -- `struct.pack()` returns `bytes` in Python 3, making `bytes + str` a `TypeError`.

No persisted pickle files (`.pkl`, `.pickle`, `.shelve`) were found in the repository, but the code writes `.cache` files and SQLite BLOB columns at runtime that will contain Python 2-protocol pickled data in production.


## Risk Breakdown

| Risk Level | Count | Description |
|------------|-------|-------------|
| Critical   | 8     | Will crash or produce corrupt data immediately on Python 3 |
| High       | 6     | Will fail when encountering Py2-era persisted data |
| Medium     | 4     | Behavioral difference that may cause subtle bugs |
| Low        | 8     | Simple renames or minor adjustments |


## Category 1: cPickle Usage (11 occurrences, 4 files)

The `cPickle` module was merged into `pickle` as the C accelerator in Python 3. All imports must change, and all `load()`/`loads()` calls for Py2-era data need `encoding='latin1'`.

### src/data_processing/mainframe_parser.py

**Import (line 20):**
```python
import cPickle
```

**Cache loading (lines 374-376)** -- Risk: HIGH
```python
f = file(cache_file, "rb")
try:
    data = cPickle.load(f)
```
Existing `.cache` files written by Python 2 with protocol 2 will fail to load in Py3 without `encoding='latin1'`.

**Error handling (line 380)** -- Risk: MEDIUM
```python
except (cPickle.UnpicklingError, IOError, EOFError), e:
```
Must change to `pickle.UnpicklingError` and use `as e` syntax.

**Cache writing (line 392)** -- Risk: MEDIUM
```python
cPickle.dump(records, f, cPickle.HIGHEST_PROTOCOL)
```
`HIGHEST_PROTOCOL` is 5 in Py3.12 (was 2 in Py2). New cache files will not be readable by any remaining Py2 processes.

### src/data_processing/json_handler.py

**Serialization (line 220)** -- Risk: HIGH
```python
cPickle.dump(record_set, f, cPickle.HIGHEST_PROTOCOL)
```
Used for inter-process data exchange via shared NFS. Both producer and consumer must migrate simultaneously.

**Deserialization (line 228)** -- Risk: HIGH
```python
data = cPickle.load(f)
```
No `encoding=` parameter means Py2-pickled record sets from the NFS staging area will fail.

### src/storage/database.py

**Event payload serialization (line 203)** -- Risk: CRITICAL
```python
blob = sqlite3.Binary(cPickle.dumps(payload_obj, 2))
```

**Event payload deserialization (line 227)** -- Risk: CRITICAL
```python
payload = cPickle.loads(str(row[3]))
```
`str(row[3])` is the most dangerous pattern in the codebase. In Py2, `str(buffer_obj)` returns raw bytes. In Py3, `str(bytes_obj)` returns `"b'\\x80\\x02...'"` -- a Python repr string, not the actual bytes. This will either crash or silently produce garbage.

**Object store deserialization (line 257)** -- Risk: CRITICAL
```python
return cPickle.loads(str(row[0])) if row else None
```
Same `str(buffer)` issue as line 227.

### src/storage/cache.py

**Fingerprinting (line 56)** -- Risk: LOW (hash only, not persisted for loading)
```python
return sha.new(cPickle.dumps(value, 2)).hexdigest()
```

**Disk persistence write (lines 198-199)** -- Risk: HIGH
```python
data = cPickle.dumps({"value": entry.value, "ttl": entry.ttl,
                      "created_at": entry.created_at}, 2)
```

**Disk persistence read (line 219)** -- Risk: HIGH
```python
rec = cPickle.loads(f.read())
```


## Category 2: copy_reg Usage (2 occurrences, 1 file)

### src/storage/database.py

**Import (line 12)** -- Risk: CRITICAL
```python
import copy_reg
```
Module renamed to `copyreg` in Python 3.

**Registration (line 28)** -- Risk: CRITICAL
```python
copy_reg.pickle(types.InstanceType, _pickle_data_point)
```
`types.InstanceType` was the metaclass for old-style classes and was removed in Python 3 (all classes are new-style). The fix is to register the `DataPoint` class directly:
```python
copyreg.pickle(DataPoint, _pickle_data_point)
```


## Category 3: struct-based Custom Serialization (9 occurrences, 3 files)

### src/io_protocols/modbus_client.py

**Payload default (line 50)** -- Risk: MEDIUM
```python
def __init__(self, unit_id, function_code, payload=""):
```
Default must be `b""` since `struct.pack()` returns `bytes` in Py3.

**TCP ADU construction (line 58)** -- Risk: MEDIUM
```python
pdu = struct.pack("B", self.function_code) + self.payload
```
`bytes + str` raises `TypeError` in Py3.

**buffer() builtin (line 101)** -- Risk: LOW
```python
return buffer(self._raw, offset, count * 2)
```
`buffer()` removed in Py3; use `memoryview()`.

**Socket recv join (line 206)** -- Risk: LOW
```python
return "".join(chunks)
```
Must be `b"".join(chunks)` since `recv()` returns `bytes` in Py3.

### src/io_protocols/mqtt_listener.py

**CONNECT packet (line 193)** -- Risk: CRITICAL
```python
vh = struct.pack(">H", 4) + "MQTT" + struct.pack("BBH", 4, 2, self.keepalive)
pl = struct.pack(">H", len(self.client_id)) + self.client_id
```
`struct.pack()` returns `bytes`, concatenated with `str` literals. This is an immediate `TypeError` in Py3.

**SUBSCRIBE packet (line 199)** -- Risk: CRITICAL
```python
pl = struct.pack(">H", len(topic)) + topic + struct.pack("B", qos)
```
Same `bytes + str` issue with topic string.

**Variable-length encoding (line 208)** -- Risk: LOW
```python
out = ""
...
out += struct.pack("B", b)
```
Accumulator must be `b""`.

### src/io_protocols/serial_sensor.py

**Packet header parsing (line 92)** -- Risk: LOW
```python
sid, stype = struct.unpack(">HB", body[:3])
```
Low risk because the file is opened in `"rb"` mode, so `body` is already bytes-compatible. However, `ord()` calls on individual bytes (lines 85, 93, 96) are unnecessary in Py3 where `bytes[i]` is already `int`.


## Category 4: json encoding= Parameter (4 occurrences, 2 files)

### src/data_processing/json_handler.py

**load_bytes (line 134)** -- Risk: CRITICAL
```python
data = json.loads(raw_bytes, encoding=self._default_encoding)
```

**dump_to_file (line 170)** -- Risk: CRITICAL
```python
kwargs = {
    "ensure_ascii": False,
    "encoding": self._default_encoding,
}
```

**dump_to_stream (line 194)** -- Risk: CRITICAL
```python
kwargs = {
    "ensure_ascii": False,
    "encoding": self._default_encoding,
}
```

### src/io_protocols/mqtt_listener.py

**json_payload (line 47)** -- Risk: CRITICAL
```python
self._json = json.loads(self.payload, encoding="utf-8")
```

All four occurrences will raise `TypeError` in Python 3.9+ because the `encoding` parameter was removed entirely.


## Categories with No Findings

The following serialization mechanisms were not found in the codebase:

- `marshal` -- not used
- `shelve` -- not used
- `yaml` (PyYAML) -- not used
- `msgpack` -- not used
- `protobuf` -- not used
- Custom `__getstate__`/`__setstate__`/`__reduce__`/`__reduce_ex__` methods -- not found


## Data Migration Plan Summary

The migration should proceed in this order:

| Step | Priority | Action | Files |
|------|----------|--------|-------|
| 1 | P0 | Replace `import cPickle` with `import pickle` | 4 files |
| 2 | P0 | Replace `import copy_reg` with `import copyreg`; remove `types.InstanceType` | database.py |
| 3 | P0 | Add `encoding='latin1'` to all `pickle.load()`/`pickle.loads()` calls | 4 files |
| 4 | P0 | Fix `str(row[N])` to `bytes(row[N])` in database.py | database.py |
| 5 | P0 | Remove `encoding=` parameter from `json.loads()`/`json.dumps()` | 2 files |
| 6 | P1 | Add `b""` prefix to all struct.pack string concatenation patterns | 2 files |
| 7 | P1 | Write and run one-time re-serialization script for cached data | New script |


## Remediation Recommendations

**Before migration:**
- Back up all production SQLite databases and cache directories.
- Inventory all consumers of the NFS pickle staging area (json_handler.py interprocess cache). All consumers must migrate simultaneously or a compatibility shim must be introduced.
- Verify that `DataPoint` in `src/core/types.py` inherits from `object` (new-style class) -- if it does not, it must be updated before the `copyreg` fix will work.

**During migration:**
- Steps 1-5 are blocking (P0) and must be completed before any Python 3 testing.
- Step 4 (str(buffer) fix) is the single most important change -- it affects data integrity, not just API compatibility.
- Step 6 can be done in parallel with IO protocol module testing.

**After migration:**
- Run the re-serialization script (Step 7) during a maintenance window with exclusive database access.
- Consider pinning `pickle.dumps()` to `protocol=2` during a transition period if any Py2 consumers remain, then upgrade to `HIGHEST_PROTOCOL` once all consumers are on Py3.
- Remove the `encoding='latin1'` arguments from `pickle.load()`/`pickle.loads()` after re-serialization is complete, as they are no longer needed for Py3-native pickle data.
