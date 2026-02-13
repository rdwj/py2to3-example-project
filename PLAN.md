# Plan: Synthesized Python 2 Migration Exercise Project

## Goal

Create a realistic Python 2.6/2.7 codebase -- a "Legacy Industrial Data Platform" -- that exercises 99+ distinct Python 2-to-3 migration patterns across diverse data domains (IoT, SCADA, mainframe, unstructured/semi-structured/structured data). This project serves as a test corpus for validating Python 2-to-3 migration skills and tooling.

## Why Synthesize Instead of Cloning

Research across 10+ GitHub repositories found no existing project that combines:
- Comprehensive language-level migration patterns (syntax, builtins, stdlib renames, bytes/str)
- Realistic domain-specific scenarios (industrial protocols, mainframe data, mixed encodings)
- An integrated codebase where modules interact (not just isolated test snippets)

The closest resources (CPython's `lib2to3` tests, `python-future` tests) cover ~50% of patterns but as isolated snippets, not realistic application code.

## Project Narrative

The project is an industrial data platform that:
- Ingests sensor data from IoT devices via serial/MQTT
- Communicates with SCADA systems via MODBUS and OPC-UA
- Processes mainframe batch files with EBCDIC encoding and COBOL-style packed decimals
- Parses CSV, XML, JSON, and unstructured text with mixed encodings
- Stores processed data in databases and file caches
- Generates reports, sends email alerts, and serves a basic web dashboard
- Runs automated tasks via a scheduler with a plugin system

This is a plausible legacy system that a real organization might need to migrate.

## Design Constraints

- All code must be syntactically valid Python 2.6/2.7
- Code does not need to actually execute (no Python 2 interpreter required), but should be structurally correct and internally consistent
- External services (serial ports, MODBUS devices, databases) are simulated with in-memory constructs and sample data files
- Each module should feel like real production code, not contrived examples -- the migration patterns should arise naturally from the domain logic
- Modules should import from each other to create realistic cross-module dependencies

---

## Directory Structure

```
py2to3-example-project/
|
|-- setup.py                          # distutils/setuptools Python 2 style
|-- README.txt                        # Old-school .txt, not .md
|-- requirements.txt                  # Pinned Py2-era dependency versions
|-- MANIFEST.in                       # Source distribution manifest
|
|-- config/
|   |-- platform.ini                  # ConfigParser format config
|   |-- logging.conf                  # Python 2 logging config
|
|-- src/
|   |-- __init__.py
|   |-- compat.py                     # Internal compatibility layer
|   |
|   |-- core/
|   |   |-- __init__.py
|   |   |-- types.py
|   |   |-- utils.py
|   |   |-- config_loader.py
|   |   |-- string_helpers.py
|   |   |-- exceptions.py
|   |   |-- itertools_helpers.py
|   |
|   |-- io_protocols/
|   |   |-- __init__.py
|   |   |-- modbus_client.py
|   |   |-- opcua_client.py
|   |   |-- serial_sensor.py
|   |   |-- mqtt_listener.py
|   |
|   |-- data_processing/
|   |   |-- __init__.py
|   |   |-- mainframe_parser.py
|   |   |-- csv_processor.py
|   |   |-- xml_transformer.py
|   |   |-- json_handler.py
|   |   |-- text_analyzer.py
|   |   |-- log_parser.py
|   |
|   |-- storage/
|   |   |-- __init__.py
|   |   |-- database.py
|   |   |-- file_store.py
|   |   |-- cache.py
|   |
|   |-- reporting/
|   |   |-- __init__.py
|   |   |-- report_generator.py
|   |   |-- email_sender.py
|   |   |-- web_dashboard.py
|   |
|   |-- automation/
|       |-- __init__.py
|       |-- scheduler.py
|       |-- script_runner.py
|       |-- plugin_loader.py
|
|-- tests/
|   |-- __init__.py
|   |-- test_core_types.py
|   |-- test_modbus.py
|   |-- test_mainframe_parser.py
|   |-- test_csv_processor.py
|   |-- test_report_generator.py
|   |-- conftest.py
|
|-- scripts/
|   |-- run_platform.py               # Main entry point
|   |-- batch_import.py               # Mainframe batch processing
|   |-- sensor_monitor.py             # IoT monitoring daemon
|
|-- data/
|   |-- sample_ebcdic.dat             # Binary EBCDIC sample
|   |-- sensor_readings.csv           # CSV with non-ASCII sensor names
|   |-- scada_config.xml              # XML with encoding declaration
|   |-- sample_records.json           # JSON with unicode data
```

---

## Migration Pattern Catalog (99 patterns)

Every pattern below will appear in at least one module. The most critical patterns (bytes/str, print, except syntax) appear in multiple modules to reflect real-world frequency.

### Category A: Syntax Changes (19 patterns)

| # | Pattern | Example | Target Module(s) |
|---|---------|---------|-------------------|
| A1 | print statement to function | `print "hello"` | reporting/report_generator, most modules |
| A2 | exec statement to function | `exec code` | automation/script_runner, reporting/report_generator |
| A3 | except comma syntax | `except Exception, e:` | core/exceptions, storage/database |
| A4 | raise syntax (two-arg) | `raise ValueError, "msg"` | core/exceptions |
| A5 | raise syntax (three-arg) | `raise E, V, T` | core/exceptions |
| A6 | backtick repr | `` `obj` `` | core/utils |
| A7 | `<>` operator | `a <> b` | core/utils |
| A8 | tuple parameter unpacking | `def f((a, b)):` | automation/script_runner |
| A9 | octal literal syntax | `0777` | storage/file_store |
| A10 | long literal suffix | `42L` | core/types, data_processing/mainframe_parser |
| A11 | unicode literal prefix | `u"text"` | core/string_helpers, data_processing/* |
| A12 | metaclass syntax | `__metaclass__ = Meta` | core/types, automation/plugin_loader |
| A13 | print `>>` redirect syntax | `print >>sys.stderr, "msg"` | reporting/report_generator |
| A14 | implicit relative imports | `from utils import ...` | multiple __init__.py files |
| A15 | `from __future__` imports | `from __future__ import print_function` | compat.py (but missing from most files) |
| A16 | set literal via `set()` constructor | `set([1,2,3])` | core/utils |
| A17 | old-style classes | `class Foo:` (no base) | core/types |
| A18 | `apply()` | `apply(f, args)` | core/utils |
| A19 | `execfile()` | `execfile("config.py")` | automation/script_runner |

### Category B: Builtin/Type Changes (16 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| B1 | `xrange()` | core/itertools_helpers, io_protocols/modbus_client |
| B2 | `raw_input()` | core/utils, scripts/run_platform |
| B3 | `long` type | core/types, data_processing/mainframe_parser |
| B4 | `unicode` type | core/string_helpers, core/types |
| B5 | `basestring` | core/string_helpers, core/types |
| B6 | `buffer()` | core/types, io_protocols/modbus_client |
| B7 | `file()` builtin | storage/file_store |
| B8 | `reduce()` in builtins | core/utils, data_processing/text_analyzer |
| B9 | `intern()` in builtins | core/utils |
| B10 | `reload()` in builtins | automation/plugin_loader |
| B11 | `StandardError` | core/exceptions |
| B12 | `dict.has_key()` | core/utils, io_protocols/opcua_client |
| B13 | `dict.iterkeys/itervalues/iteritems()` | io_protocols/serial_sensor, multiple |
| B14 | `map/filter/zip` return lists | core/itertools_helpers, data_processing/* |
| B15 | integer division `/` | io_protocols/modbus_client, storage/cache |
| B16 | `sorted()` with `cmp=` | core/types |

### Category C: Iterator/Generator Changes (8 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| C1 | `.next()` method on generators/iterators | io_protocols/serial_sensor, core/itertools_helpers |
| C2 | `__nonzero__` to `__bool__` | core/types |
| C3 | `__cmp__` removal | core/types |
| C4 | `__div__` to `__truediv__` | core/types |
| C5 | `itertools.izip/imap/ifilter` | core/itertools_helpers |
| C6 | `dict.viewkeys/viewvalues/viewitems()` | core/itertools_helpers |
| C7 | `xreadlines` | data_processing/log_parser |
| C8 | generator `throw()` API change | automation/scheduler |

### Category D: Standard Library Renames (18 patterns)

| # | Pattern | Old -> New | Target Module(s) |
|---|---------|------------|-------------------|
| D1 | `urllib`/`urllib2` | `urllib.parse`/`urllib.request` | io_protocols/opcua_client, reporting/web_dashboard |
| D2 | `ConfigParser` | `configparser` | core/config_loader |
| D3 | `Queue` | `queue` | io_protocols/opcua_client, automation/scheduler |
| D4 | `thread` | `_thread` | io_protocols/opcua_client, automation/scheduler |
| D5 | `cPickle` | `pickle` | data_processing/json_handler, storage/database |
| D6 | `StringIO`/`cStringIO` | `io.StringIO`/`io.BytesIO` | core/string_helpers, io_protocols/serial_sensor |
| D7 | `httplib` | `http.client` | io_protocols/opcua_client |
| D8 | `BaseHTTPServer` | `http.server` | reporting/web_dashboard |
| D9 | `Cookie` | `http.cookies` | reporting/web_dashboard |
| D10 | `cookielib` | `http.cookiejar` | reporting/web_dashboard |
| D11 | `HTMLParser` (module name) | `html.parser` | data_processing/xml_transformer |
| D12 | `xmlrpclib` | `xmlrpc.client` | reporting/web_dashboard |
| D13 | `repr` module | `reprlib` | data_processing/xml_transformer |
| D14 | `commands` module | `subprocess` | data_processing/log_parser |
| D15 | `sets` module | builtin `set` | core/utils |
| D16 | `md5`/`sha` modules | `hashlib` | storage/cache |
| D17 | `copy_reg` | `copyreg` | storage/database |
| D18 | `__builtin__` | `builtins` | core/config_loader |

### Category E: String/Bytes/Encoding (12 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| E1 | `str` is bytes in Py2 paradigm | Throughout, especially io_protocols/* |
| E2 | `b""` literal prefix | io_protocols/modbus_client |
| E3 | `encode()`/`decode()` behavioral differences | core/string_helpers, data_processing/* |
| E4 | Default encoding ASCII vs UTF-8 | data_processing/csv_processor |
| E5 | File I/O text vs binary mode | storage/file_store, data_processing/* |
| E6 | `struct.pack`/`unpack` with strings | io_protocols/modbus_client, io_protocols/serial_sensor |
| E7 | Socket `send()`/`recv()` types | io_protocols/mqtt_listener, io_protocols/modbus_client |
| E8 | CSV module binary mode | data_processing/csv_processor |
| E9 | `json.loads()` bytes behavior | data_processing/json_handler |
| E10 | Pickle protocol differences | storage/database, storage/cache |
| E11 | DB-API bytes/str | storage/database |
| E12 | EBCDIC/codecs conversion | data_processing/mainframe_parser |

### Category F: Function/Method Attribute Renames (6 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| F1 | `func_name` to `__name__` | automation/plugin_loader |
| F2 | `func_defaults` to `__defaults__` | automation/plugin_loader |
| F3 | `func_closure` to `__closure__` | automation/plugin_loader |
| F4 | `im_func` to `__func__` | automation/plugin_loader |
| F5 | `im_self` to `__self__` | automation/plugin_loader |
| F6 | `im_class` removed | automation/plugin_loader |

### Category G: sys Module Changes (4 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| G1 | `sys.maxint` to `sys.maxsize` | core/config_loader |
| G2 | `sys.exc_value`/`sys.exc_type` | core/exceptions, automation/scheduler |
| G3 | `sys.exitfunc` | automation/scheduler |
| G4 | `os.getcwdu()` | storage/file_store |

### Category H: Operator Module Changes (4 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| H1 | `operator.isCallable()` | automation/plugin_loader |
| H2 | `operator.sequenceIncludes()` | automation/script_runner |
| H3 | `operator.isSequenceType()` | automation/script_runner |
| H4 | `operator.isMappingType()` | automation/script_runner |

### Category I: Domain-Specific Patterns (12 patterns)

| # | Pattern | Target Module(s) |
|---|---------|-------------------|
| I1 | Binary protocol parsing with `struct` | io_protocols/modbus_client |
| I2 | Serial communication bytes boundary | io_protocols/serial_sensor |
| I3 | Socket programming bytes boundary | io_protocols/mqtt_listener |
| I4 | MODBUS register packing/unpacking | io_protocols/modbus_client |
| I5 | OPC-UA node value string/bytes | io_protocols/opcua_client |
| I6 | Fixed-width mainframe record parsing | data_processing/mainframe_parser |
| I7 | COBOL COMP-3 packed decimal | data_processing/mainframe_parser |
| I8 | CSV with non-ASCII data | data_processing/csv_processor |
| I9 | XML parsing with encoding declarations | data_processing/xml_transformer |
| I10 | JSON with non-ASCII and encoding param | data_processing/json_handler |
| I11 | Database BLOB handling | storage/database |
| I12 | Hashlib with string args | storage/cache, data_processing/text_analyzer |

---

## Module Specifications

### Phase 1: Foundation (core/ + config/ + setup.py)

#### setup.py
- Use `distutils.core.setup()` (not setuptools entry_points)
- Python 2-style metadata
- Patterns: basic Python 2 project structure

#### config/platform.ini
- ConfigParser INI file with sections for database, modbus, serial, mqtt, reporting
- Used by core/config_loader.py

#### config/logging.conf
- Python 2 `logging.config.fileConfig()` format

#### src/compat.py
- A compatibility module that wraps some Python 2-specific imports
- Demonstrates the pattern of internal compat layers in legacy code
- Patterns: A14, A15

#### src/core/types.py (12 patterns)
- `DataPoint` old-style class with `__cmp__`, `__nonzero__`, `__div__`
- `SensorReading` class with `__metaclass__` for auto-registration
- `LargeCounter` using `long` type
- Custom comparison with `sorted(cmp=...)`
- `basestring` and `unicode` type checking
- `buffer()` usage for memory-efficient data views

#### src/core/utils.py (10 patterns)
- `apply()`, `execfile()`, `reduce()`, `intern()`
- `has_key()` usage
- Backtick repr, `<>` operator
- `xrange()`, `raw_input()`
- `set()` from `sets` module
- `file()` builtin reference

#### src/core/config_loader.py (5 patterns)
- `ConfigParser.SafeConfigParser`
- `__builtin__` access
- `sys.maxint` usage
- `print` statement for config debugging
- Default encoding handling

#### src/core/string_helpers.py (6 patterns)
- Unicode/str/bytes manipulation functions
- `StringIO` and `cStringIO` usage
- `basestring` isinstance checks
- `encode()`/`decode()` chains
- `u""` string literals throughout

#### src/core/exceptions.py (6 patterns)
- `StandardError` base class
- `except Exception, e:` syntax
- `raise ValueError, "msg"` two-arg form
- `raise E, V, T` three-arg form
- `sys.exc_value`, `sys.exc_type`, `sys.exc_traceback`

#### src/core/itertools_helpers.py (8 patterns)
- `itertools.izip`, `itertools.imap`, `itertools.ifilter`
- `dict.viewkeys()`, `dict.viewvalues()`, `dict.viewitems()`
- `dict.iteritems()`, `dict.iterkeys()`
- Generator `.next()` method
- `map()`, `filter()`, `zip()` used as list producers

### Phase 2: I/O Protocols (io_protocols/)

#### src/io_protocols/modbus_client.py (8 patterns)
- MODBUS TCP client that reads holding registers
- `struct.pack`/`unpack` with string format data
- Socket `send()`/`recv()` with str (not bytes)
- CRC16 calculation using integer division
- `buffer()` for zero-copy register views
- `xrange()` for register iteration
- `thread` module for async reads
- `ConfigParser` for connection settings
- Print statements for debug logging

#### src/io_protocols/opcua_client.py (8 patterns)
- OPC-UA client using `httplib` and `urllib2`
- `xmlrpclib` for some RPC calls
- `Queue` for async node value handling
- `thread` module for subscription
- `dict.has_key()` for node attribute checks
- XML parsing with mixed encodings
- `urllib2.urlopen()` / `urllib2.Request()`
- `httplib.HTTPConnection()`

#### src/io_protocols/serial_sensor.py (6 patterns)
- Serial port reader for IoT sensor packets
- `struct` for packet header/payload parsing
- `cStringIO` for packet buffering
- Iterator `.next()` for packet stream
- `dict.iteritems()` for sensor registry
- Bytes/str confusion at serial boundary

#### src/io_protocols/mqtt_listener.py (5 patterns)
- MQTT-like message listener over raw sockets
- Socket `send()`/`recv()` with str
- `json` with `encoding` parameter
- `Queue` for message buffering
- `thread.start_new_thread()` for listener

### Phase 3: Data Processing (data_processing/)

#### src/data_processing/mainframe_parser.py (10 patterns)
- EBCDIC `codecs` decoding
- Fixed-width byte slicing on str (which is bytes in Py2)
- COBOL COMP-3 packed decimal decoding (binary math on byte arrays)
- `struct` for BCD field parsing
- `file()` with binary mode
- `cPickle` for caching parsed records
- `long` type for large account numbers
- Octal permissions `0755` on output files
- `print` for progress reporting
- `os.getcwdu()` for output directory

#### src/data_processing/csv_processor.py (6 patterns)
- CSV opened with `'rb'` mode (required in Py2)
- Custom `unicode_csv_reader` wrapping `csv.reader`
- `StringIO` for in-memory CSV processing
- `codecs.open()` for encoded output
- `encode()`/`decode()` chains
- Non-ASCII header handling with `u""` strings

#### src/data_processing/xml_transformer.py (5 patterns)
- `xml.etree.ElementTree` with encoding handling
- `HTMLParser` module (old import path)
- `repr` module (`reprlib`)
- `u""` strings in attribute comparisons
- Print for transformation logging

#### src/data_processing/json_handler.py (5 patterns)
- `json.loads()` with bytes input
- `json.dumps()` with `encoding` parameter (Py2-only)
- `ensure_ascii` behavior with unicode
- `cPickle` as fallback serializer
- `cStringIO` for streaming JSON

#### src/data_processing/text_analyzer.py (7 patterns)
- `hashlib.md5("string")` (needs bytes in Py3)
- `re` module with `re.UNICODE` flag
- Mixed encoding detection
- `commands.getoutput()` for external tool invocation
- `reduce()` as builtin for aggregation
- `map()` / `filter()` used as list producers
- `__builtin__` reference

#### src/data_processing/log_parser.py (5 patterns)
- `commands.getstatusoutput()` for log collection
- `xreadlines` for large log iteration
- `print` for parsing status
- `except Exception, e:` for parse error handling
- `os.popen()` patterns

### Phase 4: Storage (storage/)

#### src/storage/database.py (6 patterns)
- DB-API with bytes/str results (sqlite3)
- BLOB binary data insertion/retrieval
- `copy_reg` for custom type serialization
- `cPickle` for object storage
- `except Exception, e:` for DB error handling
- `StandardError` in exception hierarchy

#### src/storage/file_store.py (6 patterns)
- `file()` builtin for file creation
- Octal permissions `0777`, `0644`
- `os.getcwdu()` for path resolution
- Binary vs text mode distinctions
- `print` for store status
- `os.path` operations with unicode paths

#### src/storage/cache.py (5 patterns)
- `md5` module (not `hashlib`)
- `sha` module (not `hashlib`)
- `cPickle` with protocol version
- `long` type for cache TTL calculations
- Integer division for cache bucket math

### Phase 5: Reporting (reporting/)

#### src/reporting/report_generator.py (8 patterns)
- `print >>sys.stderr, "msg"` for error output
- `print "text"` for report output
- `exec` statement for template evaluation
- String formatting with mixed unicode/bytes
- `u""` string concatenation
- `unicode()` builtin calls
- `basestring` checks on report fields
- `reduce()` for aggregation

#### src/reporting/email_sender.py (4 patterns)
- Email module with str/bytes message bodies
- SMTP connection with string data
- `print` for send status
- `except Exception, e:` for SMTP errors

#### src/reporting/web_dashboard.py (8 patterns)
- `BaseHTTPServer.HTTPServer` / `BaseHTTPServer.BaseHTTPRequestHandler`
- `Cookie.SimpleCookie`
- `cookielib.CookieJar`
- `xmlrpclib.ServerProxy`
- `urllib.quote()` / `urllib.urlencode()`
- `print` for request logging
- `thread.start_new_thread()` for server
- HTML response with unicode content

### Phase 6: Automation (automation/)

#### src/automation/scheduler.py (6 patterns)
- `thread` module for task threads
- `Queue` for task queue
- `sys.exitfunc` for cleanup
- `sys.exc_value` in error handling
- Generator `throw()` usage
- `print` for schedule logging

#### src/automation/script_runner.py (6 patterns)
- `exec` statement for dynamic script execution
- `execfile()` for script loading
- Tuple parameter unpacking `def f((a, b)):`
- `operator.sequenceIncludes()`
- `operator.isSequenceType()`
- `operator.isMappingType()`
- `commands.getoutput()` for shell commands

#### src/automation/plugin_loader.py (10 patterns)
- `__metaclass__` for plugin registry pattern
- `reload()` builtin for plugin hot-reload
- `func_name`, `func_defaults`, `func_closure` attributes
- `im_func`, `im_self`, `im_class` attributes
- `operator.isCallable()` for plugin validation
- `isinstance()` with old-style classes
- `print` for plugin loading status

### Phase 7: Tests (tests/)

The test suite itself uses Python 2 patterns to exercise migration:

#### tests/conftest.py
- Py2-style test fixtures
- `print` statement in setup/teardown
- `unicode` string assertions

#### tests/test_core_types.py
- Tests for old-style class behavior
- `__cmp__` ordering tests
- `long` type assertions
- `assertRaises` with comma syntax

#### tests/test_modbus.py
- Binary data assertions with `str` (bytes)
- `struct` pack/unpack verification
- Register value comparison with integer division

#### tests/test_mainframe_parser.py
- EBCDIC sample data assertions
- Fixed-width field extraction tests
- COMP-3 packed decimal tests
- `file()` for test fixture loading

#### tests/test_csv_processor.py
- CSV with encoded fixtures
- `unicode_csv_reader` output tests
- `StringIO` for test input

#### tests/test_report_generator.py
- Captured `print` output assertions
- `exec` template result verification
- Unicode report content tests

### Phase 8: Scripts and Data Files

#### scripts/run_platform.py
- Main entry point with `if __name__ == "__main__"`
- `raw_input()` for interactive mode
- Imports from all modules
- `print` for status output

#### scripts/batch_import.py
- Mainframe batch processing script
- `file()` for input
- `print` for progress
- `except Exception, e:` for batch error handling

#### scripts/sensor_monitor.py
- IoT monitoring daemon
- `thread` for background monitoring
- `Queue` for sensor data
- `print` for sensor readings

#### data/sample_ebcdic.dat
- Small binary file with EBCDIC-encoded records
- Contains packed decimal fields, zone decimal, and text
- ~5-10 records for testing

#### data/sensor_readings.csv
- CSV with non-ASCII sensor names (accented characters, CJK)
- Mixed encoding scenarios
- ~20 rows of sample sensor data

#### data/scada_config.xml
- XML with `<?xml version="1.0" encoding="utf-8"?>` declaration
- SCADA system configuration with unicode node names
- Hierarchical structure for testing XML parsing

#### data/sample_records.json
- JSON with unicode strings, nested objects
- Mix of ASCII and non-ASCII content
- ~10 records representing processed data

---

## Implementation Order

1. **Directory structure** -- Create all directories via shell script
2. **Config files** -- `platform.ini`, `logging.conf`
3. **Core modules** -- `types.py`, `utils.py`, `config_loader.py`, `string_helpers.py`, `exceptions.py`, `itertools_helpers.py`, `compat.py`
4. **I/O protocol modules** -- `modbus_client.py`, `opcua_client.py`, `serial_sensor.py`, `mqtt_listener.py`
5. **Data processing modules** -- `mainframe_parser.py`, `csv_processor.py`, `xml_transformer.py`, `json_handler.py`, `text_analyzer.py`, `log_parser.py`
6. **Storage modules** -- `database.py`, `file_store.py`, `cache.py`
7. **Reporting modules** -- `report_generator.py`, `email_sender.py`, `web_dashboard.py`
8. **Automation modules** -- `scheduler.py`, `script_runner.py`, `plugin_loader.py`
9. **Test suite** -- `conftest.py`, all test files
10. **Scripts** -- `run_platform.py`, `batch_import.py`, `sensor_monitor.py`
11. **Data files** -- All sample data
12. **Top-level files** -- `setup.py`, `README.txt`, `requirements.txt`, `MANIFEST.in`
13. **Review** -- Spawn a review agent to verify all 99 patterns are covered and code is valid Python 2.6/2.7

## Implementation Approach

Each phase will be delegated to a worker subagent, then reviewed by a second subagent. The modules within each phase are independent enough to potentially parallelize some phases.

Estimated file count: ~40 files (26 Python modules, 6 test files, 3 scripts, 4 data files, 4 config/setup files, 1 README).

## Verification Criteria

After implementation, verify:
1. Every pattern from the catalog appears in at least one module
2. Critical patterns (bytes/str, print, except syntax) appear in multiple modules
3. All Python files are syntactically valid Python 2.6/2.7
4. Modules have realistic cross-module imports
5. Data files contain valid sample data
6. The project structure is coherent and the narrative holds together
