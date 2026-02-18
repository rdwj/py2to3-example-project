# Python 2→3 Conversion Unit Plan

**Target Version:** Python 3.12
**Generated:** 2026-02-18T08:35:57.986571Z
**Total Modules:** 33
**Total Conversion Units:** 11

## Executive Summary

- **Total Python 2 patterns:** 154
- **Total lines of code:** 4895
- **Estimated effort:** 174.9 hours
- **Critical path:** 13.1 days (104.6 hours)
- **Average automatable:** 52.8%

## Conversion Strategy

The migration follows a bottom-up dependency order, organized into 6 waves:

1. **Wave 1:** Core foundation modules (gateway exceptions, types, helpers)
2. **Wave 2:** Protocol and data processing layers
3. **Wave 3:** Storage and reporting layers
4. **Wave 4:** Automation and orchestration
5. **Wave 5:** Package structure and test suite
6. **Wave 6:** Utility scripts

## Gateway Module: Core Foundation

⚠️ **CRITICAL:** `src/core/exceptions.py` is the gateway module with **19 dependents** across all packages.

**Dependents:**
- All 4 io_protocols modules
- All 6 data_processing modules
- All 3 storage modules
- All 3 reporting modules
- All 3 automation modules

**Migration requirements:**
- Convert `core-foundation` unit FIRST before any dependent modules
- Comprehensive unit tests required before proceeding
- Full regression testing after conversion
- Any breaking changes here will cascade to 19+ modules

## Wave-by-Wave Breakdown

### Wave 1: Core foundation - gateway modules with highest fan-out

#### CU: core-foundation

**Description:** Core foundation modules - gateway exceptions and shared types

**Metrics:**
- Modules: 3
- Lines of code: 450
- Python 2 patterns: 24
- Risk level: high
- Estimated effort: 21.0 hours
- Automatable: 57.5%

**Risk factors:** gateway_module, 19_dependents, high_risk_modules, high_py2ism_count

**Modules:**
- `src/core/exceptions.py`
- `src/core/types.py`
- `src/core/utils.py`

**Notes:**
- Gateway module with 19 dependents
- Contains exception hierarchy using `StandardError` (removed in Py3)
- Uses legacy `sys.exc_type`, `sys.exc_value` attributes
- Has 3-argument `raise` statements and comma-style `except`
- MUST be converted before Wave 2 can begin

#### CU: core-helpers

**Description:** Core helper modules - string processing, config, itertools

**Metrics:**
- Modules: 4
- Lines of code: 380
- Python 2 patterns: 21
- Risk level: high
- Estimated effort: 18.1 hours
- Automatable: 31.4%

**Risk factors:** high_risk_modules, high_py2ism_count

**Modules:**
- `src/core/string_helpers.py`
- `src/core/config_loader.py`
- `src/core/itertools_helpers.py`
- `src/compat.py`

### Wave 2: Protocol and data processing layers - depend on core

#### CU: io-protocols

**Description:** I/O protocol clients - MODBUS, OPC-UA, Serial, MQTT

**Metrics:**
- Modules: 4
- Lines of code: 810
- Python 2 patterns: 26
- Risk level: critical
- Estimated effort: 29.2 hours
- Automatable: 22.3%

**Dependencies:** core-foundation

**Risk factors:** critical_risk_modules, high_py2ism_count

**Modules:**
- `src/io_protocols/modbus_client.py`
- `src/io_protocols/opcua_client.py`
- `src/io_protocols/serial_sensor.py`
- `src/io_protocols/mqtt_listener.py`

**Notes:**
- Binary protocol handling with struct.pack/unpack
- Thread module (renamed to _thread in Py3)
- Queue module (renamed to queue in Py3)
- Critical for real-time sensor data

#### CU: data-processing-core

**Description:** Core data processing - mainframe, CSV, XML parsers

**Metrics:**
- Modules: 3
- Lines of code: 590
- Python 2 patterns: 21
- Risk level: critical
- Estimated effort: 22.3 hours
- Automatable: 31.4%

**Dependencies:** core-foundation, core-helpers

**Risk factors:** critical_risk_modules, high_py2ism_count

**Modules:**
- `src/data_processing/mainframe_parser.py`
- `src/data_processing/csv_processor.py`
- `src/data_processing/xml_transformer.py`

**Notes:**
- EBCDIC encoding handling
- cPickle usage (merged into pickle in Py3)
- StringIO imports from Py2 modules
- Mainframe parser is critical path

#### CU: data-processing-secondary

**Description:** Secondary data processing - JSON, text, log handlers

**Metrics:**
- Modules: 3
- Lines of code: 410
- Python 2 patterns: 17
- Risk level: high
- Estimated effort: 16.7 hours
- Automatable: 23.5%

**Dependencies:** core-foundation, core-helpers

**Risk factors:** high_risk_modules

**Modules:**
- `src/data_processing/json_handler.py`
- `src/data_processing/text_analyzer.py`
- `src/data_processing/log_parser.py`

### Wave 3: Storage and reporting layers - depend on core

#### CU: storage

**Description:** Storage layer - database, file store, cache

**Metrics:**
- Modules: 3
- Lines of code: 480
- Python 2 patterns: 14
- Risk level: critical
- Estimated effort: 16.6 hours
- Automatable: 28.6%

**Dependencies:** core-foundation

**Risk factors:** critical_risk_modules

**Modules:**
- `src/storage/database.py`
- `src/storage/file_store.py`
- `src/storage/cache.py`

#### CU: reporting

**Description:** Reporting layer - report generator, email, dashboard

**Metrics:**
- Modules: 3
- Lines of code: 540
- Python 2 patterns: 20
- Risk level: high
- Estimated effort: 20.8 hours
- Automatable: 44.0%

**Dependencies:** core-foundation, core-helpers

**Risk factors:** high_risk_modules

**Modules:**
- `src/reporting/report_generator.py`
- `src/reporting/email_sender.py`
- `src/reporting/web_dashboard.py`

### Wave 4: Automation layer - orchestration and plugins

#### CU: automation

**Description:** Automation layer - scheduler, script runner, plugin loader

**Metrics:**
- Modules: 3
- Lines of code: 540
- Python 2 patterns: 11
- Risk level: critical
- Estimated effort: 16.3 hours
- Automatable: 41.8%

**Dependencies:** core-foundation

**Risk factors:** critical_risk_modules

**Modules:**
- `src/automation/scheduler.py`
- `src/automation/script_runner.py`
- `src/automation/plugin_loader.py`

### Wave 5: Package structure and tests - integration layer

#### CU: package-init

**Description:** Package __init__.py files

**Metrics:**
- Modules: 7
- Lines of code: 35
- Python 2 patterns: 0
- Risk level: low
- Estimated effort: 0.7 hours
- Automatable: 100%

**Dependencies:** core-foundation, io-protocols, data-processing-core, data-processing-secondary, storage, reporting, automation

**Modules:**
- `src/__init__.py`
- `src/core/__init__.py`
- `src/io_protocols/__init__.py`
- `src/data_processing/__init__.py`
- `src/storage/__init__.py`
- `src/reporting/__init__.py`
- `src/automation/__init__.py`

#### CU: tests

**Description:** Test suite

**Metrics:**
- Modules: 5
- Lines of code: 500
- Python 2 patterns: 0
- Risk level: low
- Estimated effort: 10.0 hours
- Automatable: 100%

**Dependencies:** core-foundation, core-helpers, data-processing-core, storage

**Modules:**
- `tests/test_types.py`
- `tests/test_utils.py`
- `tests/test_config_loader.py`
- `tests/test_mainframe_parser.py`
- `tests/test_database.py`

### Wave 6: Utility scripts - independent tooling

#### CU: scripts

**Description:** Utility scripts - lint, test runner, docs generator

**Metrics:**
- Modules: 3
- Lines of code: 160
- Python 2 patterns: 0
- Risk level: medium
- Estimated effort: 3.2 hours
- Automatable: 100%

**Modules:**
- `scripts/lint.py`
- `scripts/test_runner.py`
- `scripts/docs_generator.py`

## Critical Path Analysis

The critical path has 6 conversion units:

1. **core-foundation** (21.0 hours)
   - Core foundation modules - gateway exceptions and shared types
   - 450 LOC, 24 Py2 patterns

2. **io-protocols** (29.2 hours)
   - I/O protocol clients - MODBUS, OPC-UA, Serial, MQTT
   - 810 LOC, 26 Py2 patterns

3. **storage** (16.6 hours)
   - Storage layer - database, file store, cache
   - 480 LOC, 14 Py2 patterns

4. **reporting** (20.8 hours)
   - Reporting layer - report generator, email, dashboard
   - 540 LOC, 20 Py2 patterns

5. **automation** (16.3 hours)
   - Automation layer - scheduler, script runner, plugin loader
   - 540 LOC, 11 Py2 patterns

6. **package-init** (0.7 hours)
   - Package __init__.py files
   - 35 LOC, 0 Py2 patterns

**Total critical path time:** 104.6 hours (13.1 working days)

## Recommendations

### 1. Start with Gateway Module

Begin with `core-foundation` (CU-01) since it blocks all other work:
- Convert exception hierarchy from `StandardError` to `Exception`
- Update `sys.exc_type`/`sys.exc_value` to `sys.exc_info()`
- Convert 3-argument `raise` to Py3 syntax
- Convert comma-style `except` to parenthesized form
- Write comprehensive tests before marking as complete

### 2. Wave Execution Strategy

- **Wave 1:** Sequential (core-foundation MUST complete before core-helpers)
- **Wave 2:** Can parallelize (io-protocols, data-processing-core, data-processing-secondary are independent)
- **Wave 3:** Can parallelize (storage and reporting are independent)
- **Wave 4:** Sequential (depends on all previous waves)
- **Wave 5:** Sequential (depends on implementation modules)
- **Wave 6:** Can run anytime (scripts are independent)

### 3. Testing Strategy

For each conversion unit:
- Run existing unit tests (if any)
- Create new tests for Py2→Py3 edge cases
- Verify integration with dependencies
- Run full regression suite after gateway modules

### 4. Risk Mitigation

High-risk modules requiring extra attention:
- `src/core/exceptions.py` - 19 dependents, complex exception handling
- `src/data_processing/mainframe_parser.py` - EBCDIC, binary data, pickling
- `src/io_protocols/modbus_client.py` - Real-time binary protocols
- `src/io_protocols/serial_sensor.py` - Low-level sensor communication
- `src/storage/database.py` - Data persistence, pickle serialization

### 5. Automation Opportunities

Overall 52.8% of patterns are automatable:
- Use `2to3` or `pyupgrade` for syntax patterns (80% success rate)
- Manual review required for:
  - Exception hierarchy changes
  - Binary data handling (bytes vs str)
  - Iterator protocol changes
  - Module renames requiring import updates
