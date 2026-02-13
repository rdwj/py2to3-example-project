# Migration Readiness Report: Legacy Industrial Data Platform

## Executive Summary

- **Total Python files:** 45 (31 source + 7 test + 4 script + 3 config/setup)
- **Total lines of code:** ~8,074
- **Estimated migration effort:** **Large** (substantial semantic issues in data layer and protocol handling)
- **Recommended target version:** **3.12** (feasible but requires distutils replacement)
- **Highest-risk areas:** io_protocols (binary protocol handling, socket bytes/str), data_processing/mainframe_parser (EBCDIC, COMP-3, cPickle), data_processing/csv_processor (encoding handling), core/types (metaclass, `__cmp__`, long), storage/database (copy_reg, cPickle, types.InstanceType)

This codebase is a Python 2.7 industrial data platform spanning six packages. The migration is complicated primarily by pervasive bytes/str confusion in the protocol and data-processing layers, several abandoned or incompatible third-party dependencies, and low test coverage (~25-30%). Automated tools (2to3, futurize) can handle roughly 40% of the issues by count; the remaining 60% require manual, context-aware work -- particularly around binary protocol handling and EBCDIC/mainframe data processing.

---

## Codebase Overview

### Package Structure

| Package | Files | Lines | Description |
|---------|-------|-------|-------------|
| src/core | 7 | ~1,294 | Foundation types, utils, string helpers, config, exceptions |
| src/io_protocols | 5 | ~1,103 | MODBUS, OPC-UA, MQTT, serial sensor clients |
| src/data_processing | 7 | ~1,934 | CSV, XML, JSON, text analysis, mainframe parser, log parser |
| src/storage | 4 | ~900 | SQLite database, file store, LRU cache |
| src/automation | 4 | ~868 | Plugin system, script runner, task scheduler |
| src/reporting | 4 | ~866 | Report generator, email alerts, web dashboard |
| tests | 7 | ~585 | Unit tests (unittest-based, not pytest) |
| scripts | 4 | ~(not counted in main analysis) | Entry points |
| Other | 3 | ~(setup.py, compat.py) | Build config, compat layer |

### Dependency Graph Summary

- **7 leaf modules** (no internal dependencies): core/types, core/utils, core/string_helpers, core/config_loader, core/itertools_helpers, core/exceptions, compat
- **4 gateway modules** (high fan-in):
  - core/exceptions: imported by ~18 modules (CRITICAL gateway)
  - core/types: imported by 6 modules
  - core/config_loader: imported by 8 modules
  - core/string_helpers: imported by 6 modules
- **0 mutual import clusters** (clean dependency hierarchy)
- All packages depend on core but not on each other
- **Estimated conversion units:** 8 (core, compat, io_protocols, data_processing, storage, automation, reporting, tests)

The clean dependency hierarchy is favorable for migration. Each package can be converted independently once core is stable, and there are no circular imports to untangle.

### Test Coverage Assessment

- **5 test files** covering: core/types, io_protocols/modbus, data_processing/csv_processor, data_processing/mainframe_parser, reporting/report_generator
- **No tests for:** io_protocols/opcua_client, io_protocols/mqtt_listener, io_protocols/serial_sensor, data_processing/xml_transformer, data_processing/text_analyzer, data_processing/json_handler, data_processing/log_parser, storage/\*, automation/\*, reporting/email_sender, reporting/web_dashboard
- **Coverage estimate:** ~25-30% (only 5 of 25 source modules have dedicated tests)
- **Test framework:** unittest (not pytest)
- **Tests themselves use Py2-isms:** `cmp()`, `long()`, `basestring`, `StringIO` imports, `.decode("hex")`

The low coverage is a significant risk multiplier. Modules without tests -- especially the storage and automation packages -- will need characterization tests written before migration work begins.

---

## Python 2 Pattern Inventory

### Summary by Risk Level

| Risk Level | Category | Occurrences | Files Affected |
|-----------|----------|-------------|----------------|
| Low (automatable) | Print statements | ~187 | 35+ |
| Low (automatable) | Except comma syntax | ~66 | 25+ |
| Low (automatable) | Long literals (123L) | ~40 | 8 |
| Low (automatable) | Octal literals (0755) | 4 | 2 |
| Low (automatable) | Backtick repr | 1 | 1 |
| Low (automatable) | Diamond operator (`<>`) | 1 | 1 |
| Low (mechanical) | `dict.has_key()` | ~20 | 9 |
| Low (mechanical) | `xrange()` | 14 | 7 |
| Low (mechanical) | `raw_input()` | 2 | 1 |
| Medium (rename) | Removed/renamed stdlib imports | 41 | 20 |
| Medium (rename) | `dict.iteritems/iterkeys/itervalues` | 23 | 10 |
| Medium (semantic) | `isinstance(x, unicode/basestring)` | 66 | 15+ |
| Medium (semantic) | `long` type usage | 29 | 5 |
| Medium (semantic) | Implicit relative imports | 46 | 16 |
| Medium (semantic) | `__metaclass__` attribute | 2 | 2 |
| Medium (semantic) | `StandardError` base class | 12 | 3 |
| High (semantic) | `__cmp__` / `cmp()` / `sorted(cmp=)` | 8 | 2 |
| High (semantic) | Integer division semantics | 7 | 3 |
| High (semantic) | `file()` builtin usage | 10 | 2 |
| High (semantic) | `exec` statement form | 2 | 2 |
| High (semantic) | `raise` 3-arg form | 4 | 1 |
| High (semantic) | Tuple parameter unpacking | 2 | 1 |
| High (semantic) | Removed operator functions | 5 | 2 |
| High (semantic) | `func_name`/`im_func` attrs | 7 | 1 |
| **Critical (data)** | Socket `recv()` bytes/str | 5 | 2 |
| **Critical (data)** | `struct.pack` mixed with strings | pervasive | 4 |
| **Critical (data)** | `ord()` on byte indexing | 14 | 4 |
| **Critical (data)** | `cPickle` serialization | 11 | 4 |
| **Critical (data)** | `json` `encoding=` parameter | 6 | 2 |
| **Critical (data)** | EBCDIC codec handling | pervasive | 1 |
| **Critical (data)** | String concat of bytes | pervasive | 4+ |
| **Blocker** | `distutils` in setup.py | 1 | 1 |

### Total Issues: ~650+ occurrences across 45 files

### Low-Risk Issues (Automatable)

These can be handled by `2to3` or `futurize` with high confidence:

**Print statements (~187 occurrences).** Every source file uses bare `print` statements. 2to3's `print` fixer handles these reliably, including multi-argument forms and `print >>sys.stderr`. No manual intervention expected.

**Except comma syntax (~66 occurrences).** `except SomeError, e:` instead of `except SomeError as e:`. Purely syntactic; 2to3 handles this correctly.

**Long literals (~40 occurrences).** Integer suffixes like `123L` or `0xFFL`. Drop the `L` suffix. In Python 3 all integers are arbitrary-precision.

**Octal literals (4 occurrences).** `0755` must become `0o755`. Two files affected (file_store.py, script_runner.py).

**Backtick repr (1 occurrence).** The backtick syntax `` `x` `` for `repr(x)` appears once. Replace with `repr()`.

**Diamond operator (1 occurrence).** `<>` used instead of `!=`. One occurrence in types.py.

### Low-Risk Issues (Mechanical)

Simple find-and-replace with minor context checking:

**`dict.has_key()` (~20 occurrences).** Replace `d.has_key(k)` with `k in d`. Straightforward.

**`xrange()` (14 occurrences).** Rename to `range()`. In Python 3, `range()` is lazy (equivalent to Py2 `xrange()`).

**`raw_input()` (2 occurrences).** Rename to `input()`. Both in scripts/cli_main.py.

### Medium-Risk Issues

These require understanding context but follow known patterns:

**Removed/renamed stdlib imports (41 occurrences across 20 files).** Key renames:

| Python 2 | Python 3 |
|----------|----------|
| `ConfigParser` | `configparser` |
| `Queue` | `queue` |
| `cStringIO` / `StringIO` | `io.StringIO` / `io.BytesIO` |
| `cPickle` | `pickle` |
| `copy_reg` | `copyreg` |
| `urllib2` / `httplib` / `xmlrpclib` | `urllib.request` / `http.client` / `xmlrpc.client` |
| `thread` | `_thread` (prefer `threading`) |
| `commands` | `subprocess` |
| `md5` / `sha` | `hashlib` |
| `imp` | `importlib` |

The `cStringIO` vs `StringIO` rename is particularly tricky in this codebase because some uses need `io.BytesIO` (binary protocol buffers) while others need `io.StringIO` (text processing). Each use must be evaluated individually.

**`dict.iteritems/iterkeys/itervalues` (23 occurrences across 10 files).** Drop the `iter` prefix. In Py3, `dict.items()` returns a view (lazy), so the performance characteristics are similar.

**`isinstance(x, unicode/basestring)` (66 occurrences across 15+ files).** In Python 3, `str` is Unicode. Replace `unicode` with `str`, `basestring` with `str`. However, any code that distinguishes between `str` and `unicode` (i.e., between bytes and text) needs careful analysis -- the distinction may be load-bearing.

**`long` type usage (29 occurrences across 5 files).** Python 3 unifies `int` and `long`. Remove `long()` calls, `isinstance(x, long)` checks, and `L` suffixes. Watch for code that branches on `isinstance(x, (int, long))` -- simplify to `isinstance(x, int)`.

**Implicit relative imports (46 occurrences across 16 files).** Python 3 requires explicit relative imports. `import modbus_client` within `io_protocols/` must become `from . import modbus_client` or `from .modbus_client import ...`. These are easy to fix but easy to miss if not systematically checked.

**`__metaclass__` attribute (2 occurrences across 2 files).** Convert to `class Foo(metaclass=Meta):` syntax. Found in core/types.py and automation/plugin_system.py.

**`StandardError` base class (12 occurrences across 3 files).** Replace with `Exception`. `StandardError` was removed in Python 3.

### High-Risk Issues

These require careful manual work:

**`__cmp__` / `cmp()` / `sorted(cmp=)` (8 occurrences across 2 files).** Python 3 removed `__cmp__`. Must implement `__lt__`, `__le__`, `__gt__`, `__ge__`, `__eq__`, `__ne__` (or use `functools.total_ordering` with `__eq__` + `__lt__`). The `sorted(cmp=)` calls must use `key=functools.cmp_to_key(...)`. Found in core/types.py and data_processing/csv_processor.py.

**Integer division semantics (7 occurrences across 3 files).** Python 3's `/` operator performs true division. Code relying on `5/2 == 2` will break. Must audit and replace with `//` where integer division is intended. Found in modbus_client.py (CRC calculation), cache.py, and mainframe_parser.py. CRC and packed-decimal calculations are *especially* sensitive to this.

**`file()` builtin usage (10 occurrences across 2 files).** `file()` is removed in Py3. Replace with `open()`. Found in mainframe_parser.py and file_store.py.

**`exec` statement form (2 occurrences across 2 files).** `exec code_string` must become `exec(code_string)`. If `exec` is used with `in` (exec in globals, locals), the syntax change is more involved. Found in script_runner.py and plugin_system.py.

**`raise` 3-arg form (4 occurrences in 1 file).** `raise ExcType, exc_value, exc_tb` must become `raise ExcType(exc_value).with_traceback(exc_tb)`. Found in core/exceptions.py. Since exceptions.py is a gateway module imported by ~18 other modules, this must be handled early and carefully.

**Tuple parameter unpacking (2 occurrences in 1 file).** `def f((a, b)):` is invalid in Py3. Must unpack inside the function body. Found in script_runner.py.

**Removed operator functions (5 occurrences across 2 files).** `operator.isSequenceType()`, `operator.isMappingType()`, etc. were removed. Must replace with duck-typing checks or `isinstance()` against `collections.abc`. Found in script_runner.py and plugin_system.py.

**`func_name`/`im_func` attrs (7 occurrences in 1 file).** Renamed to `__name__`/`__func__` in Py3. Found in automation/plugin_system.py.

### Critical (Data Integrity) Issues

These are the most dangerous because they can produce silently wrong results:

**Socket `recv()` bytes/str (5 occurrences across 2 files).** In Python 2, `socket.recv()` returns `str` (which is bytes). In Python 3, it returns `bytes`. Code that concatenates recv'd data with string literals (`data += "\x00"`) will raise `TypeError` in Py3. Code that indexes into recv'd data (`data[i]`) returns `int` in Py3 instead of a single-char `str`. Found in modbus_client.py and mqtt_listener.py.

**`struct.pack` mixed with strings (pervasive across 4 files).** `struct.pack` in Py3 returns `bytes`, and the `s` format requires `bytes` input. Code that does `struct.pack("4s", some_string)` will fail if `some_string` is a Py3 `str`. All protocol handlers are affected: modbus_client.py, mqtt_listener.py, serial_sensor.py, opcua_client.py.

**`ord()` on byte indexing (14 occurrences across 4 files).** In Python 2, indexing a `str` (bytes) returns a single-char `str`, so `ord(data[0])` is needed to get the integer value. In Python 3, indexing `bytes` already returns an `int`, so `ord(data[0])` is redundant (and `ord()` of an int raises `TypeError`). Every `ord()` call on byte data must be evaluated: keep it if the input could be a single-byte `str`, remove it if the input is `bytes`. Found in modbus_client.py, mqtt_listener.py, serial_sensor.py, mainframe_parser.py.

**`cPickle` serialization (11 occurrences across 4 files).** Beyond the simple rename to `pickle`, Py3's `pickle` defaults to a newer protocol and handles `bytes`/`str` differently. Existing pickle files created by Py2 may not load correctly in Py3. This is a data compatibility issue for: database.py (BLOB storage), cache.py (cache files), mainframe_parser.py (parsed data caching), file_store.py.

**`json` `encoding=` parameter (6 occurrences across 2 files).** The `encoding` parameter was removed from `json.loads()` and `json.load()` in Python 3. Code must ensure input is `str` (decoded) before passing to json. Found in json_handler.py and mqtt_listener.py.

**EBCDIC codec handling (pervasive in 1 file).** mainframe_parser.py implements EBCDIC-to-ASCII translation, COMP-3 packed decimal parsing, and binary field extraction. This module operates entirely in the bytes domain and uses Python 2's `str`-is-bytes paradigm throughout. Every line of the parsing logic will need manual review.

**String concat of bytes (pervasive across 4+ files).** String literals used where byte literals are needed: `"\x00\x01"` should be `b"\x00\x01"` in protocol handlers. This is pervasive in io_protocols/ and parts of data_processing/.

### Blocker Issue

**`distutils` in setup.py (1 file).** `distutils` was removed in Python 3.12. The project's setup.py uses `from distutils.core import setup`. Must be replaced with `from setuptools import setup`. This is a hard blocker for the 3.12 target -- the project cannot even be installed without this fix.

---

## Version Compatibility Matrix

| Feature | 3.9 | 3.11 | 3.12 | 3.13 |
|---------|-----|------|------|------|
| Core syntax changes | OK | OK | OK | OK |
| Stdlib renames (ConfigParser, Queue, etc.) | OK | OK | OK | OK |
| distutils removal | OK | OK | **REMOVED** | REMOVED |
| cgi module | OK | Deprecated | **REMOVED** | REMOVED |
| imp module | Deprecated | Deprecated | Deprecated | REMOVED |
| asynchat/asyncore | Deprecated | Deprecated | **REMOVED** | REMOVED |

**Targeting 3.12 is feasible** but requires:
1. Replace `distutils` with `setuptools` in setup.py (blocker)
2. Replace `imp.load_source()` with `importlib` (deprecated, still works in 3.12)

Python 3.12 is the right target: it is a current LTS-track release with broad library support and will not force the additional `imp` removal that 3.13 introduces.

---

## Risk Assessment

### Top 10 Highest-Risk Modules

| Rank | Module | Risk | Reasoning |
|------|--------|------|-----------|
| 1 | io_protocols/modbus_client.py | **CRITICAL** | Binary protocol with struct.pack + str concatenation, socket.recv as str, ord() on byte indexing, integer division in CRC, buffer(), thread module |
| 2 | data_processing/mainframe_parser.py | **CRITICAL** | EBCDIC codec, COMP-3 packed decimal, cPickle caching, file() builtin, long type pervasive, ord() on bytes, os.getcwdu() |
| 3 | io_protocols/serial_sensor.py | **CRITICAL** | Binary packet parsing, ord() on bytes, cStringIO, SYNC_BYTE as str literal, .next() iterator protocol |
| 4 | io_protocols/mqtt_listener.py | **CRITICAL** | Raw TCP protocol, struct + str concat, ord() on bytes, json.loads(encoding=), Queue/thread modules |
| 5 | core/string_helpers.py | **HIGH** | Entire module is about str/unicode duality -- every function touches the bytes/str boundary. StringIO/cStringIO imports |
| 6 | io_protocols/opcua_client.py | **HIGH** | urllib2, httplib, xmlrpclib, Queue, thread -- 6 renamed stdlib modules. Mixed encoding handling |
| 7 | storage/database.py | **HIGH** | copy_reg, cPickle, types.InstanceType, StandardError, sqlite3 BLOB as buffer/bytes |
| 8 | storage/cache.py | **HIGH** | md5.new(), sha.new(), cPickle, long type, integer division, dict.iteritems |
| 9 | core/types.py | **HIGH** | __metaclass__, __cmp__, __nonzero__, __div__, long type, buffer(), basestring, cmp() |
| 10 | automation/script_runner.py | **HIGH** | exec statement, execfile(), commands module, tuple param unpacking, operator.isMappingType |

### Data Layer Risk Summary

The data layer is the **highest risk area** in this migration. Four interconnected problems make it dangerous:

1. **Binary protocol handlers.** MODBUS, MQTT, serial, and OPC-UA clients all treat socket data as `str` (bytes). In Python 3, `socket.recv()` returns `bytes`, `struct.pack()` returns `bytes`, and string literals are Unicode. Every protocol handler must be systematically converted to use `b""` literals, `bytes`/`bytearray` operations, and `bytes`-aware formatting. Getting this wrong produces silent data corruption in industrial control systems.

2. **Byte indexing semantics.** 14 uses of `ord()` on byte indexing will behave differently in Py3. In Py2, `some_bytes[i]` returns a single-char `str`, requiring `ord()` to get an integer. In Py3, `bytes[i]` returns `int` directly, so `ord(bytes[i])` raises `TypeError`. Each call must be individually assessed.

3. **EBCDIC/mainframe processing.** The mainframe parser implements EBCDIC-to-ASCII translation tables, COMP-3 packed decimal decoding, and binary fixed-width field extraction. This is the most bytes-intensive module in the codebase and every line assumes `str` is bytes. A line-by-line manual conversion is required.

4. **Serialization compatibility.** cPickle is used in 4 modules for data caching and BLOB storage. Python 3's pickle uses different default protocols and handles the bytes/str boundary differently. Any existing serialized data created by Python 2 may not deserialize correctly under Python 3. A migration strategy for existing data must be planned.

### Third-Party Dependency Risks

| Package | Pinned Version | Py3 Status | Risk |
|---------|---------------|------------|------|
| pyserial==2.7 | Old | Use pyserial>=3.0 | Low |
| paho-mqtt==1.3.1 | Old | Update to 2.x | Medium |
| pymodbus==1.3.2 | Very old | Use pymodbus>=3.0 | High |
| lxml==3.8.0 | Old | Update to 5.x | Low |
| opcua==0.98.6 | Abandoned | Use opcua-asyncio or python-opcua | High |
| SQLAlchemy==0.9.9 | Very old | Update to 2.x | High |
| simplejson==3.8.2 | Old | Update or remove (stdlib json sufficient) | Low |
| Jinja2==2.7.3 | Old | Update to 3.x | Medium |
| MarkupSafe==0.23 | Very old | Update to 2.x | Medium |
| chardet==2.3.0 | Old | Update to 5.x | Low |
| pycrypto==2.6.1 | **ABANDONED** | Replace with pycryptodome | **Critical** |
| requests==2.5.3 | Old | Update to 2.31+ | Low |
| six==1.9.0 | Old | Update or remove post-migration | Low |

**pycrypto** is a blocker -- it is unmaintained and does not support Python 3. Must be replaced with `pycryptodome` (a drop-in fork with the same `Crypto` package namespace).

**opcua** (pinned at 0.98.6) is abandoned. The community successor is `opcua-asyncio` (now called `asyncua`). This will require API changes in opcua_client.py.

**pymodbus** pinned at 1.3.2 does not support Python 3. Version 3.x has a substantially different API (async-first). The modbus_client.py module will need rework regardless of the Py2-to-Py3 syntax migration.

**SQLAlchemy** 0.9.9 is very old. The jump to 2.x introduces breaking changes (notably, the ORM query API changed significantly). The storage/database.py module should be updated carefully, potentially as a separate effort.

---

## Recommended Migration Strategy

### Phase 0: Preparation (Before Changing Any Code)

1. **Replace distutils with setuptools** in setup.py. This is the only blocker for running on Python 3.12 at all.
2. **Update requirements.txt.** Replace pycrypto with pycryptodome. Bump all packages to versions that support both Python 2.7 and Python 3. This dual-compatibility phase reduces risk.
3. **Add `from __future__` imports to all files.** Adding `print_function`, `division`, `absolute_import`, and `unicode_literals` will surface many issues while still running under Python 2.7.
4. **Write characterization tests.** Current coverage is ~25%. Before modifying any module, capture its current behavior with tests. Priority targets: storage/database.py, automation/script_runner.py, automation/plugin_system.py, io_protocols/serial_sensor.py.

### Phase 1: Core Foundation (Low Risk, High Impact)

Convert the 7 leaf modules in core/ and compat.py first. These have no internal dependencies, and everything in the codebase depends on them. Getting them right unlocks the rest of the migration.

**Order:** core/exceptions -> core/types -> core/utils -> core/string_helpers -> core/config_loader -> core/itertools_helpers -> compat.py

### Phase 2: Application Packages (Medium Risk)

Convert automation/ and reporting/ next. These have moderate Py2-isms but are not in the critical data path. They exercise the core module changes and validate the foundation.

### Phase 3: Storage Layer (High Risk)

Convert storage/database.py, storage/cache.py, storage/file_store.py. Address cPickle/pickle compatibility, buffer()/bytes conversion, and hash library updates. Plan for existing serialized data migration.

### Phase 4: Data Processing (High Risk)

Convert data_processing/ modules. The CSV processor and JSON handler have encoding-boundary issues. The mainframe parser requires the most careful, line-by-line manual work in the entire codebase.

### Phase 5: Protocol Handlers (Critical Risk)

Convert io_protocols/ last. These modules have the densest concentration of bytes/str issues and are the most likely to produce silent data corruption if converted incorrectly. Each module should be converted individually with dedicated integration testing against real or simulated protocol endpoints.

### Phase 6: Tests and Cleanup

Update all test files to Python 3. Convert from unittest to pytest (optional but recommended). Remove six and any remaining compatibility shims. Final dependency version bumps.

---

## Effort Estimate

| Phase | Modules | Estimated Effort | Confidence |
|-------|---------|-----------------|------------|
| Phase 0: Preparation | All (non-code changes) | 2-3 days | High |
| Phase 1: Core | 7 modules | 3-4 days | High |
| Phase 2: Application | 8 modules | 3-4 days | Medium |
| Phase 3: Storage | 4 modules | 3-4 days | Medium |
| Phase 4: Data Processing | 7 modules | 5-7 days | Low |
| Phase 5: Protocol Handlers | 5 modules | 5-7 days | Low |
| Phase 6: Tests/Cleanup | 7 test files + scripts | 2-3 days | Medium |
| **Total** | **45 files** | **23-32 days** | -- |

The low confidence on Phases 4 and 5 reflects the density of semantic (not syntactic) issues in those modules. Binary protocol bugs and encoding issues are time-consuming to diagnose because they often produce wrong results silently rather than raising exceptions.

---

## Recommended Next Steps

1. **Replace distutils with setuptools** in setup.py (blocker for 3.12)
2. **Update requirements.txt** -- replace pycrypto with pycryptodome, bump all packages to Py3-compatible versions
3. **Add `from __future__ import` statements** to all files (print_function, division, absolute_import, unicode_literals) to flush out issues under Py2
4. **Write characterization tests** before touching any code -- current coverage is ~25%
5. **Convert core/ leaf modules first** (they have no internal dependencies and everything depends on them)
6. **Address the data layer last** -- mainframe_parser, modbus_client, serial_sensor, and mqtt_listener require careful manual work with bytes/str boundaries
