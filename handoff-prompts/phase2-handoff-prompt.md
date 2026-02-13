I'm continuing a Python 2→3 migration of this codebase (target: Python 3.12). Phase 0 (Discovery) and Phase 1 (Foundation) are complete. All outputs are in migration-analysis/.                                                                                         
                                                                                                                                                                                                                                                                             
  Phase 1 gate check passed 7/7 — see migration-analysis/gate-check-report.md for details. Key Phase 1 deliverables:                                                                                                                                                       
                                                                                                                                                                                                                                                                           
  - setup.py migrated to setuptools, requirements.txt updated (pycrypto→pycryptodome, all deps version-bumped, six removed)
  - All 43 non-empty .py files have from __future__ import absolute_import, division, print_function, unicode_literals
  - 9 conversion units across 5 waves — see migration-analysis/conversion-plan.md and migration-analysis/critical-path.json
  - 20 characterization test files (409 functions) covering all high/critical-risk modules — see migration-analysis/test-manifest.json
  - Custom lint plugins in .lint-plugins/ with phase-specific pylintrc configs
  - Migration state updated: migration-analysis/migration-state.json (all 44 modules at Phase 1)

  For Phase 2 (Mechanical Conversion), please execute the conversion plan wave by wave:

  1. Wave 1 — CU-01 (core-foundation): Run py2to3-automated-converter on the 6 core modules (exceptions.py, types.py, config_loader.py, string_helpers.py, utils.py, itertools_helpers.py). This is the gateway unit (fan_in=40) — validate thoroughly before proceeding.
  Also convert CU-02 (compat.py) — simplify or remove the Py2/3 shim.
  2. Wave 2 — CU-03, CU-04, CU-05 (io-protocols, data-processing, storage): Convert in parallel. Key risks: database.py has silent corruption risk with str(buffer) → must use bytes() for pickle; csv_processor.py needs text-mode CSV rewrite; binary protocol modules need
   ord() removal and b"" prefixes.
  3. Wave 3 — CU-06, CU-07 (automation, reporting): Convert in parallel. plugin_loader.py needs imp→importlib; script_runner.py has exec statement and execfile().
  4. Wave 4 — CU-08 (package inits), CU-09-tests (tests): Fix implicit relative imports in __init__.py files, then convert the test suite.
  5. Wave 5 — CU-09 (scripts): Final integration validation of entry-point scripts.

  After each wave, run py2to3-bytes-string-fixer and py2to3-dynamic-pattern-resolver on the converted modules as needed. Update the migration state tracker after each CU completes. Run the gate checker when all waves are done.

  Don't move past Phase 2 without my approval.
When finished, write a prompt like this one so that I can start the next phase in a new chat.
