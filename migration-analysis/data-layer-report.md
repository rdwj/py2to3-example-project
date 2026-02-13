# Data Layer Analysis: Legacy Industrial Data Platform

## Executive Summary

The data layer is the **highest-risk area** in this migration. This codebase handles:
- Binary SCADA protocols (MODBUS TCP/RTU, MQTT v3.1.1, OPC-UA)
- RS-485 serial sensor packets with custom framing
- EBCDIC-encoded mainframe batch files (IBM z/OS via Connect:Direct)
- Multi-encoding CSV files (Latin-1, Shift-JIS, UTF-8, ASCII)
- SCADA XML configurations with HTML entities and Japanese kanji
- JSON feeds from REST gateways
- cPickle-based inter-process caching on shared NFS
- SQLite database with BLOB columns for raw protocol frames

Total data boundary points identified: 126
Critical boundaries (will break silently or produce wrong results): 54
High-risk boundaries (will raise exceptions or require significant rework): 62

## Category 1: Network/Socket I/O

### MODBUS TCP (modbus_client.py)
**Risk: CRITICAL**

The entire MODBUS client treats socket data as `str` (bytes in Py2). Key boundaries:

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 35-36 | `isinstance(byte_val, str): ord(byte_val)` | bytes_to_text | byte value extraction | Critical - Py3 str is text, not bytes |
| 38 | `xrange(8)` | internal | builtin rename | Medium - xrange removed in Py3 |
| 40,42 | `crc / 2` | internal | integer division | High - gives float in Py3 |
| 50 | `payload=""` default arg | internal | ambiguous type | Critical - must be `b""` |
| 58 | `struct.pack("B", ...) + self.payload` | text_to_bytes | bytes concat | Critical - str concat with struct output |
| 64 | `struct.pack("BB", ...) + self.payload` | internal | bytes concat | Critical |
| 89 | `len(raw_data) / 2` | internal | integer_division | High - gives float in Py3 |
| 101 | `buffer(self._raw, offset, count * 2)` | internal | bytes_only | High - buffer() removed, use memoryview |
| 126,132 | `print "MODBUS: ..."` | internal | print statement | Medium - syntax error in Py3 |
| 133,141 | `except socket.error, e:` | internal | except syntax | Medium - must use `as` keyword |
| 152-157 | `ord(response[0])`, `ord(response[1])` | bytes_to_text | byte indexing | Critical - Py3 bytes[i] returns int already |
| 164-167 | `ord(response[0])`, `ord(response[1])` | bytes_to_text | byte indexing | Critical |
| 201 | `self._sock.recv(n - got)` | ingestion | bytes_to_text | Critical - returns bytes in Py3 |
| 206 | `"".join(chunks)` | internal | bytes concat | Critical - must be `b"".join()` |
| 213 | `xrange(quantity)` | internal | builtin rename | Medium |
| 218 | `except ModbusError, e:` | internal | except syntax | Medium |

**Impact**: Every MODBUS transaction will fail. Socket `recv()` returns bytes in Py3, and the code concatenates with `""` (str) and uses `ord()` on indexing.

### MQTT Listener (mqtt_listener.py)
**Risk: CRITICAL**

Similar to MODBUS -- raw TCP protocol implementation treating all data as str.

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 9 | `import json` (usage at line 47) | bytes_to_text | encoding param | Critical - `json.loads()` encoding= removed in Py3 |
| 10 | `import Queue` | internal | module rename | Medium - `queue` in Py3 |
| 11 | `import thread` | internal | module rename | Medium - `_thread` in Py3 |
| 47 | `json.loads(self.payload, encoding="utf-8")` | bytes_to_text | encoding param | Critical - encoding= removed in Py3 |
| 49 | `except (ValueError, TypeError), e:` | internal | except syntax | Medium |
| 69 | `Queue.Queue(maxsize=maxq)` | internal | module rename | Medium |
| 75-78 | `Queue.Full`, `Queue.Empty` | internal | module rename | Medium |
| 91,100 | `xrange(...)` | internal | builtin rename | Medium |
| 132 | `except socket.error, e:` | internal | except syntax | Medium |
| 134 | `self._sock.send(self._mk_connect())` | text_to_bytes | socket send | Critical - send() requires bytes in Py3 |
| 138 | `ord(ack[3])` | bytes_to_text | byte indexing | Critical - Py3 bytes[i] returns int |
| 193 | `struct.pack(">H", 4) + "MQTT"` | internal | bytes concat | Critical - "MQTT" must be b"MQTT" |
| 194 | `struct.pack(">H", len(...)) + self.client_id` | internal | bytes concat | Critical - client_id is str |
| 199 | `struct.pack(">H", len(topic)) + topic` | internal | bytes concat | Critical - topic is str in Py2 |
| 203-204 | `struct.pack(">H", len(topic)) + topic` | internal | bytes concat | Critical |
| 208 | `out = ""` | internal | binary accumulator | Critical - must be `b""` |
| 211 | `n = n / 128` | internal | integer division | High - gives float in Py3 |
| 214 | `out += struct.pack("B", b)` | internal | bytes concat | Critical - concatenating struct output with str |
| 221 | `self._sock.recv(1)` | ingestion | byte read | Critical - returns bytes |
| 226 | `first + "\x00"` | internal | bytes concat | Critical - must be `b"\x00"` |
| 227 | `body = ""` | internal | binary accumulator | Critical - must be `b""` |
| 229 | `self._sock.recv(rem - len(body))` | ingestion | byte read | Critical |
| 243 | `self._sock.recv(1)` | ingestion | byte read | Critical |
| 246 | `ord(b)` | bytes_to_text | byte indexing | Critical - Py3 bytes[0] is int |
| 267 | `ord(pkt[0]) & 0xF0` | bytes_to_text | byte indexing | Critical |
| 270-271 | `struct.unpack(">H", pkt[2:4])` | internal | bytes slice | OK if pkt is bytes |
| 277 | `except (struct.error, IndexError), e:` | internal | except syntax | Medium |

### OPC-UA Client (opcua_client.py)
**Risk: HIGH**

HTTP-based with multi-encoding XML responses. Uses renamed Py2 standard library modules.

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 8 | `import httplib` | internal | module rename | Medium - `http.client` in Py3 |
| 9 | `import urllib` | internal | module rename | Medium - `urllib.parse` in Py3 |
| 10 | `import urllib2` | internal | module rename | Medium - `urllib.request` in Py3 |
| 11 | `import xmlrpclib` | internal | module rename | Medium - `xmlrpc.client` in Py3 |
| 12 | `import Queue` | internal | module rename | Medium |
| 13 | `import thread` | internal | module rename | Medium |
| 39 | `self.attributes.has_key(name)` | internal | dict method | Medium - removed in Py3 |
| 42 | `self.attributes.has_key(name)` | internal | dict method | Medium |
| 74 | `self._items.has_key(node_id)` | internal | dict method | Medium |
| 110 | `urllib.urlencode(...)` | text_to_bytes | renamed function | Medium - `urllib.parse.urlencode` |
| 112-116 | `urllib2.Request/urlopen` | ingestion | bytes_to_text | High - `response.read()` returns bytes in Py3 |
| 119 | `except urllib2.URLError, e:` | internal | except syntax | Medium |
| 139 | `urllib.quote(node_id, safe="")` | text_to_bytes | renamed function | Medium - `urllib.parse.quote` |
| 141 | `urllib2.urlopen(url).read()` | ingestion | bytes_to_text | High - returns bytes in Py3 |
| 160 | `except xmlrpclib.Fault, e:` | internal | except syntax | Medium |
| 180 | `httplib.HTTPConnection(...)` | internal | module rename | Medium |
| 185 | `except (httplib.HTTPException, socket.error), e:` | internal | except syntax | Medium |
| 192 | `t.encode("utf-8")` | text_to_bytes | encoding | Low - correct pattern |
| 221 | `isinstance(raw, unicode)` | internal | type check | High - `unicode` doesn't exist in Py3 |
| 236 | `urllib.urlencode(...)` | text_to_bytes | renamed function | Medium |
| 239 | `urllib2.urlopen(...)` | ingestion | bytes_to_text | High |

### Serial Sensor (serial_sensor.py)
**Risk: CRITICAL**

Binary packet parser using `ord()` extensively on what should be byte data.

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 8 | `from cStringIO import StringIO` | internal | import | Medium - use `io.BytesIO` |
| 13 | `SYNC_BYTE = "\xAA"` | internal | constant | Critical - must be `b"\xAA"` |
| 42 | `print "SERIAL: ..."` | internal | print statement | Medium |
| 54 | `" ".join("%02X" % ord(b) for b in self.payload)` | bytes_to_text | formatting | Critical - Py3 bytes iteration yields int, ord() would fail on int |
| 68 | `self._buf = StringIO()` | internal | buffer type | High - needs `io.BytesIO` |
| 75 | `def next(self):` | internal | iterator protocol | High - Py3 uses `__next__()` |
| 80 | `if b != SYNC_BYTE` | internal | comparison | Critical - comparing str with str, but both must become bytes |
| 85 | `plen = ord(lb)` | bytes_to_text | byte indexing | Critical - Py3 bytes read returns bytes, `b[0]` is int |
| 92 | `struct.unpack(">HB", body[:3])` | internal | bytes slice | OK if body is bytes |
| 93 | `ord(body[-1])` | bytes_to_text | byte indexing | Critical |
| 96 | `chk ^= ord(c)` | bytes_to_text | byte iteration | Critical - Py3 bytes iteration yields int |
| 128 | `except IOError, e:` | internal | except syntax | Medium |
| 144 | `SensorPacketStream(self._port).next()` | internal | iterator protocol | High - must use `next()` builtin |
| 167 | `self._registry.iteritems()` | internal | dict method | High - removed in Py3 |
| 172 | `self._registry.has_key(sid)` | internal | dict method | Medium |
| 180 | `self._registry.iteritems()` | internal | dict method | High |

## Category 2: EBCDIC / Mainframe (mainframe_parser.py)
**Risk: CRITICAL**

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 20 | `import cPickle` | internal | import | Medium - use `pickle` in Py3 |
| 41 | `OUTPUT_FILE_MODE = 0755` | internal | octal literal | Medium - syntax error in Py3, use `0o755` |
| 84 | `self._field_index.has_key(name)` | internal | dict method | Medium |
| 115 | `self._parsed_fields.has_key(field_name)` | internal | dict method | Medium |
| 155 | `result = 0L` | internal | long literal | Medium - `L` suffix removed in Py3 |
| 156 | `[ord(b) for b in raw_bytes]` | bytes_to_text | byte iteration | Critical - Py3 bytes iteration yields int, `ord(int)` raises TypeError |
| 159 | `xrange(len(byte_array) - 1)` | internal | builtin rename | Medium |
| 162 | `result * 100L + long(...)` | internal | long type | Medium - `long` removed |
| 168 | `result * 10L + long(final_digit)` | internal | long type | Medium |
| 201 | `return 0L` | internal | long literal | Medium |
| 203 | `result = 0L` | internal | long literal | Medium |
| 204 | `[ord(b) for b in raw_bytes]` | bytes_to_text | byte iteration | Critical - same as line 156 |
| 206 | `xrange(len(byte_array) - 1)` | internal | builtin rename | Medium |
| 208 | `result * 10L + long(digit)` | internal | long type | Medium |
| 214 | `result * 10L + long(digit)` | internal | long type | Medium |
| 241 | `0xFFFFFFFFL` | internal | long literal | Medium |
| 246 | `LargeCounter(0L)` | internal | long literal | Medium |
| 267 | `f = file(file_path, "rb")` | ingestion | file open | High - `file()` builtin removed in Py3 |
| 293 | `long(self._error_count.value)` | internal | long type | Medium |
| 325 | `value = long(raw_value)` | internal | long type | Medium |
| 333 | `value = long(raw_value)` | internal | long type | Medium |
| 340 | `except Exception, e:` | internal | except syntax | Medium |
| 346 | `isinstance(account_raw, (int, long))` | internal | type check | High - `long` removed in Py3 |
| 347 | `long(account_raw)` | internal | long type | Medium |
| 374 | `f = file(cache_file, "rb")` | ingestion | file open | High - `file()` removed |
| 376 | `cPickle.load(f)` | ingestion | deserialization | High - Py2 pickles may not load in Py3 |
| 380 | `except (cPickle.UnpicklingError, IOError, EOFError), e:` | internal | except syntax | Medium |
| 390 | `f = file(cache_file, "wb")` | egression | file open | High - `file()` removed |
| 392 | `cPickle.dump(records, f, cPickle.HIGHEST_PROTOCOL)` | egression | serialization | High - protocol 2 max in Py2 |
| 395 | `os.chmod(cache_file, OUTPUT_FILE_MODE)` | internal | octal literal | Medium - cascading from line 41 |
| 406 | `os.getcwdu()` | internal | unicode cwd | High - removed in Py3, use `os.getcwd()` |
| 412 | `f = file(summary_path, "w")` | egression | file open | High - `file()` removed |
| 435 | `long(self._record_count.value)` | internal | long type | Medium |

**Key insight**: The `ord()` calls in `decode_comp3` and `decode_zoned_decimal` are the correct pattern for Py2 but redundant in Py3 (bytes iteration already yields ints). The fix is to remove the `ord()` calls or add a compatibility wrapper. However, if these functions receive `str` (text) in Py3 instead of `bytes`, the logic breaks entirely -- the caller must ensure bytes input.

## Category 3: Encoding/Decoding (string_helpers.py)
**Risk: HIGH**

This entire module exists because of Py2's str/unicode duality. Every function needs rewriting.

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 12 | `from StringIO import StringIO` | internal | import | Medium - use `io.StringIO` |
| 13 | `from cStringIO import StringIO as FastStringIO` | internal | import | Medium - use `io.BytesIO` |
| 39 | `isinstance(raw_bytes, str)` | internal | type check | Critical - Py3 `str` is text, not bytes; should check `bytes` |
| 59 | `isinstance(value, unicode)` | internal | type check | High - `unicode` doesn't exist in Py3 |
| 61 | `isinstance(value, basestring)` | internal | type check | High - `basestring` removed in Py3 |
| 63 | `unicode(value)` | internal | builtin call | High - `unicode` removed |
| 69 | `isinstance(value, str) and not isinstance(value, unicode)` | internal | type check | Critical - this Py2 "is bytes?" idiom is meaningless in Py3 |
| 71 | `isinstance(value, unicode)` | internal | type check | High |
| 73 | `str(value)` | internal | conversion | Medium - semantics differ |
| 80-81 | `isinstance(value, unicode)` ... `.encode(encoding)` | text_to_bytes | encoding | High |
| 82 | `isinstance(value, basestring)` | internal | type check | High |
| 84 | `str(value)` | internal | conversion | Medium |
| 97 | `isinstance(label, unicode)` | internal | type check | High |
| 98 | `label.decode(u"utf-8", u"replace")` | bytes_to_text | decoding | High - Py3 str has no `.decode()` |
| 122-127 | Multiple `isinstance(part, unicode)` / `isinstance(part, basestring)` | internal | type check | High |
| 127 | `unicode(part)` | internal | builtin call | High |
| 135 | `isinstance(f, basestring)` | internal | type check | High |
| 135 | `unicode(f)` | internal | builtin call | High |
| 148 | `StringIO()` for text buffer | internal | buffer | High - Py3 `io.StringIO` only accepts str |
| 150 | `buf.write(safe_encode(initial))` | internal | buffer write | High - writing bytes to text StringIO |
| 156 | `FastStringIO()` for binary buffer | internal | buffer | High - use `io.BytesIO` |
| 171 | `isinstance(text, unicode)` | internal | type check | High |
| 172 | `text.decode(u"utf-8", u"replace")` | bytes_to_text | decoding | High |

## Category 4: CSV Processing (csv_processor.py)
**Risk: HIGH**

The entire `unicode_csv_reader`/`unicode_csv_writer` pattern is a Py2 workaround that must be replaced.

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 20 | `from StringIO import StringIO` | internal | import | Medium |
| 29 | `CSV_READ_MODE = "rb"` | ingestion | file mode | High - Py3 csv needs text mode `"r"` with `newline=""` |
| 37 | `_BOM_UTF8 = "\xef\xbb\xbf"` | internal | constant | Critical - must be `b"\xef\xbb\xbf"` |
| 38 | `_BOM_UTF16_LE = "\xff\xfe"` | internal | constant | Critical - must be `b"\xff\xfe"` |
| 39 | `_BOM_UTF16_BE = "\xfe\xff"` | internal | constant | Critical - must be `b"\xfe\xff"` |
| 54-56 | `unicode_csv_reader` yielding decoded cells | bytes_to_text | CSV wrapper | Critical - entire approach changes in Py3 |
| 71 | `isinstance(cell, unicode)` | internal | type check | High |
| 73 | `isinstance(cell, str)` | internal | type check | High - in Py3, str is text |
| 120 | `isinstance(col, unicode)` | internal | type check | High |
| 123 | `col.decode("utf-8", "replace")` | bytes_to_text | decoding | High |
| 124 | `self._mappings.has_key(key)` | internal | dict method | Medium |
| 132 | `self._transforms.has_key(internal_name)` | internal | dict method | Medium |
| 165 | `f = open(file_path, CSV_READ_MODE)` | ingestion | file open | High - Py3 csv needs `open(f, 'r', newline='', encoding=...)` |
| 181 | `except DataError, e:` | internal | except syntax | Medium |
| 194 | `isinstance(csv_text, unicode)` | internal | type check | High |
| 195 | `csv_text.encode(encoding)` | text_to_bytes | encoding | Medium - correct intent but Py3 csv takes str |
| 197 | `StringIO(csv_text)` | internal | buffer | High - Py3 csv needs `io.StringIO` with text |
| 211 | `except DataError, e:` | internal | except syntax | Medium |
| 226 | `codecs.open(file_path, "wb", encoding=...)` | egression | file open | High - `"wb"` + encoding is contradictory in Py3 |
| 229 | `encoded_header = header_line.encode(encoding, "replace")` | text_to_bytes | encoding | High - double-encoding: codecs.open already encodes |
| 236 | `isinstance(value, unicode)` | internal | type check | High |
| 238 | `isinstance(value, str)` | internal | type check | High - semantics reversed |
| 295 | `header[:3] == _BOM_UTF8` | internal | comparison | Critical - comparing bytes (from "rb" read) with str constant |
| 297-299 | BOM comparisons | internal | comparison | Critical - same issue |

**Key insight**: The Py3 csv module handles unicode natively. The entire `unicode_csv_reader`/`unicode_csv_writer` wrapper becomes unnecessary. But the file open modes change: Py3 csv requires `open(f, 'r', newline='', encoding='...')`.

## Category 5: JSON Handling (json_handler.py)
**Risk: HIGH**

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 19 | `import cPickle` | internal | import | Medium - use `pickle` |
| 20 | `from cStringIO import StringIO` | internal | import | Medium - use `io.BytesIO` |
| 64 | `self.metadata.has_key(key)` | internal | dict method | Medium |
| 134 | `json.loads(raw_bytes, encoding=self._default_encoding)` | bytes_to_text | encoding param | Critical - encoding= removed in Py3 |
| 135 | `except (ValueError, TypeError), e:` | internal | except syntax | Medium |
| 170-171 | `"encoding": self._default_encoding` in json.dumps kwargs | text_to_bytes | encoding param | Critical - encoding= removed in Py3 |
| 179 | `isinstance(json_str, unicode)` | internal | type check | High |
| 199-201 | Same encoding= and unicode check pattern | text_to_bytes | encoding param | Critical |
| 220 | `cPickle.dump(record_set, f, cPickle.HIGHEST_PROTOCOL)` | egression | serialization | High - protocol 2 max in Py2 |
| 228 | `cPickle.load(f)` | ingestion | deserialization | High - cross-version pickle compatibility |
| 250 | `record.has_key(field)` | internal | dict method | Medium |
| 275 | `record.iteritems()` | internal | dict method | High - removed in Py3 |
| 278 | `value_transforms.has_key(new_key)` | internal | dict method | Medium |
| 281 | `except Exception, e:` | internal | except syntax | Medium |
| 304 | `data.iterkeys()` | internal | dict method | High - removed in Py3 |

## Category 6: Database Layer (database.py)
**Risk: HIGH**

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 12 | `import copy_reg` | internal | import | Medium - renamed to `copyreg` in Py3 |
| 13 | `import cPickle` | internal | import | Medium - use `pickle` |
| 28 | `copy_reg.pickle(types.InstanceType, ...)` | internal | registration | Critical - `types.InstanceType` removed in Py3 (no old-style classes) |
| 98 | `except StandardError, e:` | internal | except syntax + class | Medium - except syntax; also `StandardError` removed |
| 105 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 129 | `except Exception, e:` | internal | except syntax | Medium |
| 143 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 153 | `sqlite3.Binary(raw_frame)` | internal | BLOB handling | Low - still works in Py3 |
| 160 | `except Exception, e:` | internal | except syntax | Medium |
| 193 | `str(row[0])` converting buffer to str | bytes_to_text | BLOB read | Critical - Py3 `str(bytes_obj)` gives repr, not content |
| 203 | `cPickle.dumps(payload_obj, 2)` | egression | serialization | High |
| 204 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 227 | `cPickle.loads(str(row[3]))` | bytes_to_text | deserialization | Critical - `str(buffer)` in Py3 gives repr |
| 240 | `cPickle.dumps(obj, 2)` | egression | serialization | High |
| 241 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 257 | `cPickle.loads(str(row[0]))` | bytes_to_text | deserialization | Critical - same as line 227 |

**Key insight**: The `str(row[0])` pattern for extracting BLOB data is the #1 silent corruption risk. In Py2, `str(buffer_obj)` returns the raw bytes. In Py3, `str(bytes_obj)` returns `"b'\\x...'"` -- the repr, not the content. Must use `bytes(row[0])` instead.

## Category 7: Cache Layer (cache.py)
**Risk: HIGH**

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 17 | `import md5` | internal | import | High - standalone `md5` module removed in Py3 |
| 18 | `import sha` | internal | import | High - standalone `sha` module removed in Py3 |
| 19 | `import cPickle` | internal | import | Medium - use `pickle` |
| 39 | `long(time.time())` | internal | long type | Medium - `long` removed |
| 40 | `long(time.time())` | internal | long type | Medium |
| 42 | `self.access_count = 0L` | internal | long literal | Medium |
| 46 | `long(time.time())` | internal | long type | Medium |
| 49 | `long(time.time())` | internal | long type | Medium |
| 50 | `1L` | internal | long literal | Medium |
| 56 | `sha.new(cPickle.dumps(value, 2)).hexdigest()` | internal | hashing | Critical - `sha.new()` removed in Py3 |
| 69 | `0L, 0L, 0L` | internal | long literals | Medium |
| 73 | `md5.new(key).hexdigest()` | internal | hashing | Critical - `md5.new()` removed in Py3 |
| 74 | `hash_val / self._num_buckets` | internal | integer division | High - gives float in Py3 |
| 80 | `1L` | internal | long literal | Medium |
| 88 | `1L` | internal | long literal | Medium |
| 104 | `long(time.time()) + 1L` | internal | long type | Medium |
| 105 | `self._store.iteritems()` | internal | dict method | High - removed in Py3 |
| 114 | `1L` | internal | long literal | Medium |
| 118 | `(self._hits * 100) / total` | internal | integer division | High - gives float in Py3 |
| 140 | `hashlib.md5(raw_key).hexdigest()` | internal | hashing | High - needs bytes input in Py3 |
| 193 | `entries.iteritems()` | internal | dict method | High - removed in Py3 |
| 198-199 | `cPickle.dumps(...)` to disk | egression | serialization | High |
| 206 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 219 | `cPickle.loads(f.read())` from disk | ingestion | deserialization | High |
| 222 | `long(time.time())` | internal | long type | Medium |
| 233 | `except StandardError, e:` | internal | except syntax + class | Medium |
| 244 | `except OSError, e:` | internal | except syntax | Medium |
| 250 | `self._cache._store.iteritems()` | internal | dict method | High - removed in Py3 |

## Category 8: File Store (file_store.py)
**Risk: HIGH**

| Line | Pattern | Direction | Boundary | Risk |
|------|---------|-----------|----------|------|
| 25 | `DIR_PERMISSIONS = 0755` | internal | octal literal | Medium - syntax error in Py3, use `0o755` |
| 26 | `FILE_PERMISSIONS = 0644` | internal | octal literal | Medium |
| 27 | `FILE_PERMISSIONS_RESTRICTED = 0600` | internal | octal literal | Medium |
| 37 | `os.getcwdu()` | internal | unicode cwd | High - removed in Py3, use `os.getcwd()` |
| 38 | `isinstance(root_path, str)` | internal | type check | Critical - Py3 `str` is text, not bytes |
| 39 | `root_path.decode("utf-8")` | bytes_to_text | decoding | Critical - Py3 `str` has no `.decode()` |
| 90 | `f = file(dest, "w")` | egression | file open | High - `file()` builtin removed in Py3 |
| 92 | `isinstance(content, unicode)` | internal | type check | High |
| 93 | `content.encode(encoding)` | text_to_bytes | encoding | Medium |
| 99 | `except IOError, e:` | internal | except syntax | Medium |
| 106 | `f = file(dest, "wb")` | egression | file open | High - `file()` removed |
| 121 | `f = file(dest, "wb")` | egression | file open | High |
| 129 | `isinstance(dp.tag, unicode)` | internal | type check | High |
| 138 | `except (IOError, struct.error), e:` | internal | except syntax | Medium |
| 144 | `f = file(dest, "w")` | egression | file open | High |
| 146 | `isinstance(content, unicode)` | internal | type check | High |
| 162 | `f = file(src, "r")` | ingestion | file open | High |
| 167 | `except IOError, e:` | internal | except syntax | Medium |
| 175 | `f = file(src, "rb")` | ingestion | file open | High |
| 201 | `total_bytes, total_files = 0L, 0` | internal | long literal | Medium |
| 207 | `long(os.path.getsize(...))` | internal | long type | Medium |

## Hardcoded Byte Constants

These string literals must become bytes literals (prefix with `b`):

| File | Line | Constant | Purpose |
|------|------|----------|---------|
| modbus_client.py | 50 | `payload=""` | Empty payload default |
| serial_sensor.py | 13 | `"\xAA"` | Sync byte |
| mqtt_listener.py | 193 | `"MQTT"` | Protocol name in CONNECT packet |
| mqtt_listener.py | 208 | `out = ""` | Binary accumulator |
| mqtt_listener.py | 226 | `"\x00"` | Null byte |
| mqtt_listener.py | 227 | `body = ""` | Binary accumulator |
| csv_processor.py | 37 | `"\xef\xbb\xbf"` | UTF-8 BOM marker |
| csv_processor.py | 38 | `"\xff\xfe"` | UTF-16 LE BOM marker |
| csv_processor.py | 39 | `"\xfe\xff"` | UTF-16 BE BOM marker |

## Silent Corruption Risks

These are the boundaries most likely to produce **wrong results** rather than exceptions, making them the hardest to catch in testing:

1. **`str(buffer_obj)` for BLOB extraction** (database.py lines 193, 227, 257): In Py3, `str(bytes_obj)` returns the repr `"b'\\x...'"` instead of raw bytes. Data appears to "work" but is garbage.

2. **Integer division in CRC/hash calculations** (modbus_client.py lines 40/42, cache.py line 74): `crc / 2` returns a float in Py3, causing bitwise operations to fail or produce wrong CRC values. MODBUS frames with bad CRC are silently dropped by the PLC.

3. **`json.loads(bytes, encoding=...)` removal**: In Py3, passing `encoding=` raises `TypeError` immediately -- not silent, but the fix of just removing the parameter changes behavior if the input contains non-UTF-8 byte sequences.

4. **BOM comparison with str constants** (csv_processor.py lines 295-299): `header[:3] == _BOM_UTF8` compares bytes (from `"rb"` read) against str constants. In Py3, this is always `False`, so BOM detection silently fails and the wrong encoding is used.

## Recommendations

### Immediate Actions (Before Any Code Changes)
1. Write characterization tests for every boundary point marked CRITICAL
2. Collect sample data files for MODBUS, MQTT, serial, EBCDIC, and pickle formats
3. Document the expected bytes/str type at every function boundary in io_protocols/

### Phase 3 Priorities (in order)
1. Fix socket `recv()` boundaries in modbus_client.py and mqtt_listener.py -- every network transaction is broken
2. Fix serial_sensor.py byte parsing (`ord()`, `SYNC_BYTE`, `StringIO`)
3. Fix mainframe_parser.py `ord()` loops and `file()` calls
4. Replace csv_processor.py unicode wrapper with Py3-native csv handling
5. Remove `json.loads`/`json.dumps` `encoding=` parameters
6. Fix database.py BLOB handling (`str(buffer)` to `bytes()`)
7. Replace `md5`/`sha` modules with `hashlib` in cache.py
8. Update string_helpers.py type checks for Py3 str/bytes
9. Fix all `file()` calls to use `open()` across file_store.py and mainframe_parser.py
10. Convert octal literals from `0755` to `0o755` form
