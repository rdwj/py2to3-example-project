Implement the following plan:

# Phase 3: Semantic Fixes & Runtime Validation Plan

## Context

Phase 2 mechanically converted all 44 modules to valid Python 3.12 syntax (gate: PASS 7/7), but **no code has actually been executed yet**. Phase 3 makes it run. Exploration identified three blocking issues and a test-fix-test cycle to work through.

## Step 0: Environment Setup

Create venv, install dependencies, install pytest.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install pytest
```

## Step 1: Fix Inconsistent Import Paths (12 source modules + 3 scripts)

**Problem:** `data_processing/`, `automation/`, and `reporting/` modules use `from core.X import Y` — bare package names that only resolve when `src/` is on `sys.path`. But tests add the **project root** to `sys.path`, so only `from src.core.X import Y` works (the convention used by `storage/` and `io_protocols/`). Two conventions = runtime `ModuleNotFoundError`.

**Fix:** Standardize on `from src.core.X` everywhere. Change the 12 affected source modules and 3 scripts.

**Source modules** (`from core.X` → `from src.core.X`):
- `src/automation/scheduler.py` (L19)
- `src/automation/script_runner.py` (L18)
- `src/automation/plugin_loader.py` (L18)
- `src/data_processing/log_parser.py` (L23-24)
- `src/data_processing/json_handler.py` (L23-24)
- `src/data_processing/mainframe_parser.py` (L24-26)
- `src/data_processing/csv_processor.py` (L20-22)
- `src/data_processing/text_analyzer.py` (L24-26)
- `src/data_processing/xml_transformer.py` (L23-25)
- `src/reporting/email_sender.py` (L19-21)
- `src/reporting/web_dashboard.py` (L25-26)
- `src/reporting/report_generator.py` (L18-20)

**Scripts** (change `sys.path` from `os.pardir, "src"` to `os.pardir`, then prefix all bare imports with `src.`):
- `scripts/run_platform.py` (L21 path fix + L23-33 imports: 11 lines)
- `scripts/sensor_monitor.py` (L24 path fix + L26-29 imports: 4 lines)
- `scripts/batch_import.py` (L23 path fix + L25-29 imports: 3 lines)

(`scripts/generate_ebcdic_data.py` is self-contained, no changes needed.)

**Verification:** `python3 -c "from src.data_processing.csv_processor import CsvProcessor; print('OK')"`

## Step 2: Fix Py2 Patterns in Characterization Tests (2 files)

**2a. `tests/test_scheduler_characterization.py`:**
- L19: `import Queue` → `import queue`
- 8 instances of `Queue.Queue()` → `queue.Queue()`
- 4 instances of `gen.next()` → `next(gen)`

**2b. `tests/test_serial_sensor_characterization.py`:**
- 6 instances of `stream.next()` → `next(stream)`
- Review `build_packet()` helper and byte string literals — verify they use bytes (`b""`) not str, since source module now expects bytes throughout

**No changes needed** to `test_itertools_helpers_characterization.py` — `.next()` only in docstrings, actual code calls wrapper functions that already use `next()`.

## Step 3: First Test Run (Diagnostic)

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -100
```

Capture and categorize all failures:
- ImportError (should be resolved by Steps 1-2)
- TypeError (bytes/str mismatches)
- AttributeError (leftover Py2 methods)
- Behavioral assertion failures (Py2 vs Py3 semantics)
- External dependency failures (serial ports, MQTT broker, etc.)

## Step 4: Fix Runtime Failures Iteratively

Fix in dependency order: core → storage → io_protocols → data_processing → automation/reporting.

For external dependency tests (Modbus hardware, MQTT broker, serial port), add conditional skips with `@pytest.mark.skipif` or document as waivers. Focus on tests exercisable with in-memory constructs.

For `@pytest.mark.py2_behavior` assertion failures, update expected values to Py3 semantics where the behavioral difference is expected (e.g., `type(u"text")` is `str` in Py3, integer division returns float, `dict.keys()` returns a view not a list).

## Step 5: Validate Bytes/Str Boundaries

After tests are passing, focused validation of the highest-risk modules:
- `database.py`: SQLite BLOB roundtrip (pickle.dumps → store → retrieve → pickle.loads)
- `serial_sensor.py`: Binary packet parse/CRC (via characterization tests)
- `mainframe_parser.py`: EBCDIC decode paths (via `data/sample_ebcdic.dat`)
- `csv_processor.py`: Text-mode CSV with encoding parameter

## Step 6: Full Green Test Suite

```bash
python3 -m pytest tests/ -v --tb=short
```

Target: all tests pass, or have documented waivers for external dependencies.

## Step 7: Gate Check & Documentation

- Update `migration-state.json` (all 44 modules → Phase 3)
- Generate `phase3-gate-check-report.json` and `.md`
- Write Phase 4 handoff prompt

**Commit:** `chore: Complete Phase 3 (Semantic Fixes) of Python 2→3 migration`

## Execution Strategy

**Wave A (parallel, Steps 0-2):**
- Sub-agent 1: venv setup + import path fixes (Step 0 + Step 1)
- Sub-agent 2: test file fixes (Step 2a + 2b)

**Wave B (sequential, Steps 3-7):**
- Run tests, triage, fix iteratively
- Gate check when green

## Critical Files

| File | Role |
|------|------|
| `tests/conftest.py` | sys.path contract (adds project root) |
| `src/data_processing/csv_processor.py` | Representative of 12 broken imports |
| `tests/test_scheduler_characterization.py` | `import Queue` + `.next()` |
| `tests/test_serial_sensor_characterization.py` | bytes/str in test helpers + `.next()` |
| `migration-analysis/migration-state.json` | Phase tracking |


If you need specific details from before exiting plan mode (like exact code snippets, error messages, or content you generated), read the full transcript at: /Users/wjackson/.claude/projects/-Users-wjackson-Developer-code-translation-tests-py2to3-example-project/a3e370db-9e6c-41c0-b3d8-88befc733c58.jsonl
