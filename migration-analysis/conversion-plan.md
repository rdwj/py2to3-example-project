# Conversion Plan: Legacy Industrial Data Platform

**Date:** 2026-02-12
**Target:** Python 3.12
**Scope:** 44 modules, 8,074 lines, 699 Py2-isms across 53 categories

## Executive Summary

The migration is organized into **9 conversion units** across **5 waves**. No circular dependencies exist in the codebase -- the dependency graph is strictly hierarchical, flowing from leaf core modules through consumer packages to entry-point scripts.

The **critical path** runs through core-foundation -> data-processing -> package-inits -> tests -> scripts, with an estimated **28-49 person-hours** of effort. The bottleneck is CU-04 (data-processing), the largest unit at 2,119 lines with 143 Py2-isms including EBCDIC handling and cPickle serialization boundaries.

Of the 699 total issues, **213 (30.5%) are automatable** via tools like 2to3/pyupgrade (print statements, except syntax, long literals), while **486 require manual review** (bytes/str boundaries, import renames, serialization changes, behavioral shifts).

| Metric | Value |
|--------|-------|
| Conversion units | 9 |
| Waves | 5 |
| Total effort (low) | 59 person-hours |
| Total effort (high) | 103 person-hours |
| Calendar time (1 dev) | 3-5 weeks |
| Calendar time (2 devs) | 2-3 weeks |
| Automatable issues | 213 (30.5%) |
| Manual-review issues | 486 (69.5%) |

---

## Wave-by-Wave Breakdown

### Wave 1: Foundation

**Purpose:** Convert all leaf modules with zero internal dependencies. These are the gateway modules that every other package imports from.

| Unit | Modules | Lines | Py2-isms | Risk | Effort |
|------|---------|-------|----------|------|--------|
| **CU-01** core-foundation | 6 | 1,209 | 101 | HIGH | 8-14h |
| **CU-02** compat-shim | 1 | 107 | 13 | MEDIUM | 1-2h |

**CU-01: core-foundation** -- GATEWAY UNIT (fan_in=40)

This is the single most important unit. A regression here cascades to every consumer package.

Modules and key concerns:
- `src/core/exceptions.py` (fan_in=19) -- except comma syntax, raise two-arg, sys.exc_type removal
- `src/core/config_loader.py` (fan_in=8) -- ConfigParser->configparser, __builtin__->builtins, 15 print stmts
- `src/core/types.py` (fan_in=7) -- __cmp__/__nonzero__/__div__ protocol modernization, long literals, metaclass
- `src/core/string_helpers.py` (fan_in=6) -- **Highest semantic complexity.** Every isinstance check must be redesigned for the Py3 str/bytes model. 20 semantic bytes/str issues.
- `src/core/utils.py` (fan_in=0) -- sets.Set->set, backtick repr, diamond operator, apply(), intern()
- `src/core/itertools_helpers.py` (fan_in=0) -- itertools.izip/imap/ifilter, dict.viewkeys, iterator.next()

Testing strategy before proceeding to Wave 2:
1. Verify exception class hierarchy (all custom exceptions inherit correctly)
2. Verify DataPoint/SensorReading construction, comparison, and serialization
3. Verify safe_decode/safe_encode with bytes, str, and mixed inputs
4. Verify config loading with configparser module

**CU-02: compat-shim**

`src/compat.py` is a standalone Py2/3 shim with no internal dependents. Post-migration decision: simplify to Py3-only or delete entirely and inline Py3 equivalents where used.


### Wave 2: Protocol and Processing Layer

**Purpose:** Convert the three major consumer packages that depend only on Wave 1 core modules. These can run in parallel with up to 3 developers.

| Unit | Modules | Lines | Py2-isms | Risk | Effort |
|------|---------|-------|----------|------|--------|
| **CU-03** io-protocols | 4 | 934 | 95 | HIGH | 10-18h |
| **CU-04** data-processing | 6 | 2,119 | 143 | HIGH | 14-24h |
| **CU-05** storage | 3 | 773 | 102 | HIGH | 8-14h |

**CU-03: io-protocols** -- Binary Protocol Specialists

This unit has the highest density of bytes/str boundary issues. 42 boundary points across 4 modules, with 31 rated critical.

Key conversion patterns:
- Remove all `ord()` calls on bytes indexing (14 instances across modbus, mqtt, serial)
- Change all `""` to `b""` in packet construction paths
- Change `"".join(chunks)` to `b"".join(chunks)` for socket recv accumulation
- Fix integer division in CRC calculations (`/` -> `//`)
- Replace `buffer()` with `memoryview()`
- Rename `from cStringIO import StringIO` to `from io import BytesIO`
- Fix struct.pack + str concatenation to struct.pack + bytes

**CU-04: data-processing** -- CRITICAL PATH BOTTLENECK

Largest unit. Contains the most diverse set of migration challenges.

Module-level breakdown:
- `mainframe_parser.py` (438 lines, 55 issues) -- Highest issue count in codebase. EBCDIC byte handling, 17 long literals, cPickle, file() builtin, os.getcwdu()
- `csv_processor.py` (319 lines, 15 issues) -- Py3 csv requires text mode. The unicode CSV wrapper pattern needs complete replacement.
- `json_handler.py` (324 lines, 20 issues) -- json.loads/dumps encoding= removal, cPickle staging files
- `xml_transformer.py` (307 lines, 20 issues) -- HTMLParser import, dict.has_key, unicode checks
- `text_analyzer.py` (296 lines, 18 issues) -- commands module -> subprocess, map/filter iterators
- `log_parser.py` (435 lines, 15 issues) -- commands module, os.popen, xreadlines

**CU-05: storage** -- Silent Corruption Risk

Contains the highest-risk single issue in the entire migration:

> **WARNING:** `database.py` lines 227 and 257 use `cPickle.loads(str(row[N]))`. In Py2, `str(buffer_obj)` returns raw bytes. In Py3, `str(bytes_obj)` returns `"b'\\x80\\x02...'"` -- a repr string, causing **silent data corruption**. Must change to `pickle.loads(bytes(row[N]))`.

Additional concerns:
- `cache.py`: md5.new/sha.new module removal, hashlib requires bytes input
- `file_store.py`: 6 file() builtin replacements, octal literal syntax, os.getcwdu()


### Wave 3: Automation and Reporting

**Purpose:** Convert higher-level consumer packages. These depend only on Wave 1, so they can start as soon as Wave 1 completes -- they do NOT need to wait for Wave 2.

| Unit | Modules | Lines | Py2-isms | Risk | Effort |
|------|---------|-------|----------|------|--------|
| **CU-06** automation | 3 | 758 | 93 | HIGH | 6-10h |
| **CU-07** reporting | 3 | 677 | 74 | HIGH | 6-10h |

**CU-06: automation**

Most diverse Py2 idiom set per unit:
- `plugin_loader.py` (39 issues, 16 different categories): imp->importlib, metaclass attr, func_name/func_defaults/func_closure, im_func/im_self/im_class, operator.isCallable, reload()
- `script_runner.py`: exec statement, execfile(), tuple parameter unpacking (rare in modern code), operator.isMappingType/isSequenceType
- `scheduler.py`: sys.exc_type/exc_value, sys.exitfunc, thread->_thread/threading, Queue->queue

**CU-07: reporting**

- `report_generator.py` (37 issues, critical density 16.8/100 lines): 11 unicode type refs, 4 basestring checks, print>>stderr, exec statement, 4 reduce() calls
- `web_dashboard.py` (22 issues): 5 removed stdlib imports (thread, BaseHTTPServer, Cookie, cookielib, xmlrpclib)
- `email_sender.py` (15 issues): unicode encoding for MIME content


### Wave 4: Package Facades and Tests

**Purpose:** Wire up the converted modules through package __init__ files, then convert the test suite.

| Unit | Modules | Lines | Py2-isms | Risk | Effort |
|------|---------|-------|----------|------|--------|
| **CU-08** package-inits | 6 | 78 | 22 | LOW | 1-2h |
| **CU-09-tests** tests | 7 | 695 | 56 | MEDIUM | 3-5h |

**CU-08: package-inits**

All 22 issues are `SEMANTIC_IMPLICIT_RELATIVE_IMPORT`. Mechanical fix: add `.` prefix to every import. Example: `from types import DataPoint` -> `from .types import DataPoint`.

**CU-09-tests: tests**

Key conversion points:
- `test_mainframe_parser.py`: 13 `long` type references need `isinstance(x, int)` rewrites
- `test_core_types.py`: 5 `cmp()` builtin usages need comparison operator rewrites
- `conftest.py`: `str.decode('hex')` -> `bytes.fromhex()`
- `test_csv_processor.py`, `test_report_generator.py`: `from StringIO import StringIO` -> `from io import StringIO`

After this wave, the test suite should be running under Python 3.12.


### Wave 5: Entry Points and Build System

**Purpose:** Final integration validation. Convert entry-point scripts and resolve the distutils blocker.

| Unit | Modules | Lines | Py2-isms | Risk | Effort |
|------|---------|-------|----------|------|--------|
| **CU-09** scripts-and-setup | 5 | 617 | 1 | MEDIUM | 2-4h |

The 4 scripts (`batch_import.py`, `generate_ebcdic_data.py`, `run_platform.py`, `sensor_monitor.py`) have **zero Py2-isms** -- they already use `from __future__` imports. The work here is integration testing.

The single issue is in `setup.py`: `from distutils.core import setup` must become `from setuptools import setup`. distutils was removed in Python 3.12, making this a hard blocker.

---

## Critical Path

```
CU-01 (core-foundation)        [8-14h]  GATEWAY
    |
    v
CU-04 (data-processing)        [14-24h] BOTTLENECK
    |
    v
CU-08 (package-inits)          [1-2h]
    |
    v
CU-09-tests (tests)            [3-5h]
    |
    v
CU-09 (scripts-and-setup)      [2-4h]
                                --------
                        Total:  28-49h
```

The critical path runs through data-processing because it is the largest unit. The **alternative near-critical path** runs through io-protocols (24-43h), making it a secondary risk if binary protocol work proves more difficult than expected.

Wave 3 units (automation, reporting) are **not on the critical path** because they depend only on Wave 1 and can run in parallel with Wave 2 without affecting the schedule.

---

## Gateway Unit Warnings

### CU-01: core-foundation (fan_in=40)

This is the only gateway unit. Its 4 key modules are imported by:

| Module | fan_in | Imported by |
|--------|--------|-------------|
| exceptions.py | 19 | All non-leaf packages |
| config_loader.py | 8 | data_processing (4 modules), reporting (1), core __init__ |
| types.py | 7 | io_protocols (3), data_processing (1), storage (1), reporting (1), core __init__ |
| string_helpers.py | 6 | data_processing (3), reporting (3) |

**Recommendation:** Do not proceed to Wave 2 until:
1. All 6 core modules pass Python 3.12 import + basic functionality smoke tests
2. The public API surface (exception classes, DataPoint constructor, safe_decode/safe_encode signatures) is verified compatible
3. Any API changes are documented for downstream unit converters

---

## Effort Estimates by Unit

| Unit | Automatable | Manual | Total Issues | Lines | Effort (hours) |
|------|-------------|--------|-------------|-------|----------------|
| CU-01 core-foundation | 30 | 71 | 101 | 1,209 | 8-14 |
| CU-02 compat-shim | 0 | 13 | 13 | 107 | 1-2 |
| CU-03 io-protocols | 29 | 66 | 95 | 934 | 10-18 |
| CU-04 data-processing | 40 | 103 | 143 | 2,119 | 14-24 |
| CU-05 storage | 32 | 70 | 102 | 773 | 8-14 |
| CU-06 automation | 40 | 53 | 93 | 758 | 6-10 |
| CU-07 reporting | 22 | 52 | 74 | 677 | 6-10 |
| CU-08 package-inits | 0 | 22 | 22 | 78 | 1-2 |
| CU-09-tests tests | 20 | 36 | 56 | 695 | 3-5 |
| CU-09 scripts-and-setup | 0 | 1 | 1 | 617 | 2-4 |
| **Totals** | **213** | **486** (1) | **699** (1) | **8,074** (1) | **59-103** |

(1) Issue total includes the 1 CRITICAL distutils issue in setup.py.

---

## Risk Heatmap

| Risk Level | Units |
|------------|-------|
| **HIGH** | CU-01 (core-foundation), CU-03 (io-protocols), CU-04 (data-processing), CU-05 (storage), CU-06 (automation), CU-07 (reporting) |
| **MEDIUM** | CU-02 (compat-shim), CU-09-tests (tests), CU-09 (scripts-and-setup) |
| **LOW** | CU-08 (package-inits) |

Six of nine units are rated HIGH. This reflects the pervasive nature of Py2 idioms across the codebase rather than any single catastrophic issue. The actual silent-corruption risks are concentrated in:

1. **database.py** `str(buffer)` -> `bytes()` for pickle deserialization (CU-05)
2. **mqtt_listener.py** struct.pack + str concatenation in packet construction (CU-03)
3. **csv_processor.py** binary-mode CSV incompatible with Py3 csv module (CU-04)

---

## Key Blockers

| Blocker | Location | Severity | Resolution |
|---------|----------|----------|------------|
| distutils removed in 3.12 | setup.py:13 | CRITICAL | Replace with setuptools |
| pycrypto (abandoned) | requirements/external | CRITICAL | Replace with pycryptodome |

Both blockers are in the final wave (CU-09) and do not gate any source module conversion.

---

## Recommended Conversion Strategy per Unit

For each unit, the recommended approach is:

1. **Run automated tools first** (2to3 --nofix=all --fix=print --fix=except, pyupgrade) to handle the 213 automatable issues
2. **Manual review** of all semantic changes, especially bytes/str boundaries
3. **Write/update tests** as you go -- each module should have a passing test before moving to the next
4. **Validate imports** by importing the module under Python 3.12 and checking for ImportError
5. **Run the existing test suite** after each unit to catch regressions

For the gateway unit (CU-01), add an intermediate validation step between modules: convert exceptions.py first, verify it imports, then types.py, etc.
