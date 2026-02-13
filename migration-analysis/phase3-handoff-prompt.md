# Phase 3 Handoff Prompt: Semantic Fixes & Runtime Validation

Copy everything below the line into a new chat to begin Phase 3.

---

## Context

This is Phase 3 (Semantic Fixes) of a Python 2→3 migration for the "Legacy Industrial Data Platform" project at `/Users/wjackson/Developer/code-translation-tests/py2to3-example-project`.

**Phases completed:**
- Phase 0 (Discovery): PASS — codebase analyzed, 699 Py2-isms inventoried across 53 categories
- Phase 1 (Foundation): PASS — future imports, test scaffolds, lint rules, conversion plan
- Phase 2 (Mechanical Conversion): PASS 7/7 — all 44 modules across 9 CUs converted, all 65 .py files parse as valid Python 3.12

**Key artifacts:**
- `migration-analysis/migration-state.json` — all 44 modules at Phase 2
- `migration-analysis/phase2-gate-check-report.json` — Phase 2 gate: PASS 7/7
- `migration-analysis/conversion-plan.json` — CU definitions and wave order
- 20 characterization test files in `tests/test_*_characterization.py`
- 7 original test files in `tests/test_*.py`

## Phase 3 Goal

Make the mechanically-converted code **actually run** under Python 3.12. Phase 2 ensured all files parse as valid Python 3 syntax, but they have not been executed. Phase 3 fixes runtime failures and validates semantic correctness.

## Phase 3 Tasks

### 1. Fix Remaining Py2 Patterns in Characterization Tests

The 20 characterization test files were generated in Phase 1 to capture Py2 behavior. Several still contain Py2 runtime patterns that would cause `ImportError` or `AttributeError` under Python 3:

**Known issues:**
- `test_scheduler_characterization.py`: `import Queue` (should be `import queue`), `Queue.Queue()` (should be `queue.Queue()`), `gen.next()` (should be `next(gen)`)
- `test_serial_sensor_characterization.py`: `stream.next()` (should be `next(stream)`)
- `test_itertools_helpers_characterization.py`: `iterator.next()` (should be `next(iterator)`)
- `test_opcua_client_characterization.py`: `Queue.Queue` references in docstrings
- `test_mqtt_listener_characterization.py`: `Queue.Queue` references in docstrings

Scan all 20 characterization tests for remaining Py2 patterns and fix them. Use the `py2to3-automated-converter` skill on the test files if needed, or fix manually.

### 2. Run the Full Test Suite Under Python 3.12

```bash
cd /Users/wjackson/Developer/code-translation-tests/py2to3-example-project
python3 -m pytest tests/ -v --tb=long 2>&1 | head -200
```

Expect failures. Categorize them:
- **Import errors**: Missing or renamed modules/functions
- **TypeError**: bytes/str mismatches at boundaries
- **AttributeError**: Removed Py2 methods (.next(), .has_key(), etc.)
- **Behavioral differences**: Different return types (dict views vs lists, map/filter returning iterators, integer division)
- **Encoding errors**: EBCDIC, mixed-encoding, BOM edge cases

### 3. Fix Runtime Failures

For each category of failure, apply the appropriate skill:

- **Bytes/str boundary fixes**: Use `py2to3-bytes-string-fixer` on affected modules
- **Dynamic patterns** (metaclass, exec, eval, cmp, __nonzero__): Use `py2to3-dynamic-pattern-resolver`
- **Remaining import issues**: Fix manually or use `py2to3-library-replacement`

Priority order for fixing:
1. Core foundation (CU-01) — everything depends on this
2. Storage layer (CU-05) — especially `database.py` BLOB handling
3. IO protocols (CU-03) — binary protocol correctness
4. Data processing (CU-04) — CSV, JSON, EBCDIC handling
5. Everything else

### 4. Validate Bytes/Str Boundaries

The highest-risk semantic area. Key modules to stress-test:

| Module | Risk | What to validate |
|--------|------|-----------------|
| `database.py` | CRITICAL | SQLite BLOB roundtrip: pickle.dumps → store → retrieve → pickle.loads |
| `serial_sensor.py` | HIGH | Binary packet parsing: bytes indexing, CRC calculation |
| `modbus_client.py` | HIGH | Modbus register read/write: bytes construction, ord() removal |
| `mqtt_listener.py` | HIGH | MQTT payload: topic decoding, binary message handling |
| `csv_processor.py` | HIGH | Text-mode CSV: encoding parameter, newline handling |
| `mainframe_parser.py` | HIGH | EBCDIC decode: codepage handling, mixed-encoding records |
| `string_helpers.py` | MEDIUM | safe_encode/safe_decode: bytes↔str boundary |
| `email_sender.py` | MEDIUM | MIME encoding: str vs bytes for MIMEText body |

### 5. Run Encoding Stress Tests (if time permits)

Use `py2to3-encoding-stress-tester` on the data layer modules to exercise:
- EBCDIC (cp500, cp037, cp1047) encoding paths in `mainframe_parser.py`
- Mixed-encoding file handling in `log_parser.py`
- BOM detection in `csv_processor.py` and `text_analyzer.py`
- Binary data that looks like valid UTF-8

### 6. Update Migration State

After fixing runtime failures, update `migration-state.json`:
- Record decisions about bytes/str boundary handling
- Record any waivers for tests that can't pass without external dependencies (Modbus hardware, MQTT broker, etc.)
- Note which tests require mocking external services

### 7. Run Phase 3 Gate Checker

When all fixes are applied and tests pass (or have documented waivers), run the gate checker:
- Use `py2to3-gate-checker` for the Phase 2→3 transition
- Gate criteria: full test suite passes under Py3, no encoding errors, bytes/str boundaries resolved

## Important Notes

- `from __future__` imports are still present intentionally — they'll be removed in Phase 4
- `src/compat.py` has been simplified to Py3-only but still exists — it'll be evaluated for removal in Phase 4
- Tests marked with `@pytest.mark.py2_behavior` capture Py2-specific behavior — some may need assertion updates for Py3 semantics (e.g., `is_text(u"text")` now checks `isinstance(value, str)` which is `True` for all strings in Py3)
- Don't move past Phase 3 without my approval
- When finished, write a prompt like this one so that I can start the next phase in a new chat
