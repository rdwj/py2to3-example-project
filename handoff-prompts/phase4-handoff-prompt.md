# Phase 4: Cleanup & Finalization — Handoff Prompt

## Context

Phases 0–3 of the Python 2→3 migration are complete. The codebase is a fully functional Python 3.11+ project: 517 tests pass, 0 failures, all 44 modules at Phase 3 in `migration-state.json`. Phase 4 removes the scaffolding — `__future__` imports, compatibility shims, Py2 idioms — and modernizes the code for Python 3.12.

**Project:** Legacy Industrial Data Platform
**Location:** `/Users/wjackson/Developer/code-translation-tests/py2to3-example-project`
**Target:** Python 3.12
**Current state:** 517 tests green, 163 pytest warnings (unregistered `py2_behavior` marker)

## Step 1: Remove `from __future__` Imports (64 files)

Every `.py` file carries the same line:
```python
from __future__ import absolute_import, division, print_function, unicode_literals
```

These are no-ops in Python 3. Remove from all 64 files:
- 30 source modules under `src/`
- 5 scripts (`setup.py`, `scripts/*.py`)
- 29 test files (`tests/conftest.py`, `tests/test_*.py`, `.lint-plugins/`)

**Risk:** None. All four futures are default behavior in Python 3.

**Verification:** `grep -r "from __future__" src/ scripts/ tests/ setup.py` should return zero results.

## Step 2: Simplify `src/compat.py`

The compat shim was reduced to Py3-only code in Phase 2 but still contains dead re-exports. Current contents (76 lines):

**Dead code to remove** (zero imports found in codebase):
- `PY3 = True` constant
- `string_types`, `text_type`, `binary_type`, `integer_types` type aliases
- `OrderedDict` re-export (use `collections.OrderedDict` directly)
- `json` re-export
- `md5`, `sha1` re-exports from hashlib

**Actually imported by other modules:**
- `configparser` — used by `src/core/config_loader.py`
- `queue` — used by `src/automation/scheduler.py`, `src/io_protocols/opcua_client.py`
- `pickle` — used by `src/storage/database.py`, `src/storage/cache.py`
- `BytesIO`, `StringIO` — used across data_processing and io_protocols
- `ensure_bytes()` — used by data_processing modules
- `ensure_text()` — used by string_helpers

**Decision:** Replace compat imports with direct stdlib imports throughout the codebase, then delete `src/compat.py` entirely. The two utility functions (`ensure_bytes`, `ensure_text`) should move to `src/core/string_helpers.py` where they logically belong. If any module only imports `pickle` or `queue` from compat, change to `import pickle` / `import queue` directly.

After inlining all imports, delete `src/compat.py` and remove it from `src/__init__.py`.

**Verification:** `grep -r "from src.compat\|from compat" src/ scripts/ tests/` should return zero results.

## Step 3: Remove `(object)` Base Classes (33 classes, 12 files)

In Python 3, `class Foo(object):` is equivalent to `class Foo:`. Remove the explicit `(object)` inheritance from all 33 classes:

| File | Classes |
|------|---------|
| `src/core/config_loader.py` | `PlatformConfig` |
| `src/core/types.py` | `DataPoint`, `SensorReading`, `LargeCounter` |
| `src/io_protocols/opcua_client.py` | `OpcUaNode`, `OpcUaSubscription`, `OpcUaClient` |
| `src/io_protocols/modbus_client.py` | `ModbusFrame`, `RegisterBank`, `ModbusClient` |
| `src/io_protocols/mqtt_listener.py` | `MqttMessage`, `MqttSubscription`, `MqttListener` |
| `src/io_protocols/serial_sensor.py` | `SensorPacket`, `SensorPacketStream` |
| `src/data_processing/csv_processor.py` | `CsvFieldMapper`, `CsvProcessor`, `_UnicodeWriter` |
| `src/data_processing/json_handler.py` | `JsonRecordSet`, `JsonHandler` |
| `src/data_processing/log_parser.py` | `LogEntry`, `LogFilter`, `LogParser` |
| `src/data_processing/mainframe_parser.py` | `CopybookLayout`, `MainframeRecord`, `MainframeParser` |
| `src/data_processing/text_analyzer.py` | `TextFingerprint`, `TextAnalyzer` |
| `src/data_processing/xml_transformer.py` | `XmlNodeMapper`, `XmlTransformer` |

Also check test files and `ByteSource(object)` in `tests/test_serial_sensor_characterization.py`.

**Risk:** None. `class Foo(object)` and `class Foo:` are identical in Python 3.

**Exception:** Do NOT remove `(object)` from classes that use `metaclass=` — but grep found none in this codebase.

## Step 4: Remove `u""` String Prefixes (~1,421 occurrences)

In Python 3, `u"text"` and `"text"` are identical. Remove the `u` prefix from all string literals across the codebase.

**Heaviest files** (by occurrence count):
- `tests/test_report_generator_characterization.py` (~76)
- `tests/test_string_helpers_characterization.py` (~72)
- `tests/test_csv_processor.py` (~28)
- `src/core/string_helpers.py` (~22)
- Remaining spread across all test files

**Approach:** Use `replace_all` edits or a scripted find-replace. Be careful NOT to change `b""` byte literals — only `u""` / `u''` prefixes.

**Risk:** None. The `u` prefix is a no-op in Python 3.

## Step 5: Register or Remove `@pytest.mark.py2_behavior` (163 tests)

163 test functions carry `@pytest.mark.py2_behavior`, causing 163 pytest warnings. Two options:

**Option A (recommended): Register the marker.** Create `pyproject.toml` with:
```toml
[tool.pytest.ini_options]
markers = [
    "py2_behavior: Tests that document behavior differences between Python 2 and Python 3",
]
```

This preserves the documentation value of the markers and silences the warnings.

**Option B: Remove all markers.** If the Py2 behavior documentation is no longer valuable, strip all 163 `@pytest.mark.py2_behavior` decorators. This is a larger diff for minimal functional gain.

## Step 6: Modernize String Formatting (Optional, ~331 `%` uses)

Convert `%` formatting to f-strings in source modules. Focus on the reporting layer where formatting is heaviest:
- `src/reporting/web_dashboard.py` (13 uses)
- `src/reporting/report_generator.py` (3 uses)
- `src/reporting/email_sender.py` (3 uses)
- `src/storage/file_store.py` (error messages)
- `src/core/config_loader.py` (warning messages)

**Do not** convert `%` formatting in test files — the diff would be enormous (~300 changes) for no functional benefit.

**Risk:** Low. Test coverage validates correctness.

## Step 7: Migrate `setup.py` to `pyproject.toml` (Optional)

`setup.py` currently uses setuptools and works fine. Optionally migrate to the modern `pyproject.toml` format:
- Move all metadata from `setup()` call to `[project]` table
- Keep `python_requires = ">=3.12"`
- Move test config (if Step 5 Option A chosen) into same file

**Risk:** Medium. Build system changes need validation (`pip install -e .` still works).

## Step 8: Final Validation

```bash
# All tests still green
python3 -m pytest tests/ -v --tb=short

# No __future__ imports remain
grep -r "from __future__" src/ scripts/ tests/ setup.py

# No compat imports remain (if compat.py deleted)
grep -r "from src.compat\|from compat" src/ scripts/ tests/

# No (object) base classes remain
grep -rn "class.*\(object\)" src/ tests/

# No u"" prefixes remain
grep -rn "u\"" src/ tests/ scripts/ | grep -v "b\"\|# " | head -20

# Zero pytest warnings about py2_behavior
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Target: 517 tests pass, 0 failures, 0 warnings.

## Step 9: Gate Check & Documentation

- Update `migration-state.json` (all 44 modules → Phase 4)
- Generate `phase4-gate-check-report.json` and `.md`
- Gate criteria:
  1. All tests pass (517/517)
  2. Zero `from __future__` imports
  3. `compat.py` removed or simplified
  4. Zero `(object)` base classes
  5. Zero `u""` string prefixes
  6. Zero pytest warnings
  7. No regressions

**Commit:** `chore: Complete Phase 4 (Cleanup & Finalization) of Python 2→3 migration`

## Execution Strategy

**Wave 1 (parallel, mechanical cleanup):**
- Agent 1: Remove `__future__` imports from all 64 files
- Agent 2: Remove `(object)` base classes from all 33 classes
- Agent 3: Remove `u""` prefixes from all files

**Wave 2 (sequential, requires judgment):**
- Inline compat.py imports and delete the module
- Register pytest markers (or remove)
- Optionally modernize string formatting in reporting layer

**Wave 3 (validation):**
- Full test suite
- Grep verification checks
- Gate check report generation

## Critical Files

| File | Role |
|------|------|
| `src/compat.py` | Compatibility shim — target for deletion |
| `src/core/string_helpers.py` | Receives `ensure_bytes`/`ensure_text` from compat |
| `tests/conftest.py` | Test configuration, sys.path, markers |
| `setup.py` | Build system (optional pyproject.toml migration) |
| `migration-analysis/migration-state.json` | Phase tracking |

## Out of Scope

- **Type annotations**: Valuable but large scope. Better as a separate follow-up.
- **Comprehensive f-string conversion in tests**: ~300 changes for zero functional benefit.
- **Architectural refactoring**: Phase 4 is cleanup, not redesign.
