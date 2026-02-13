I'm continuing a Python 2→3 migration of this codebase (target: Python 3.12). Phase 0 (Discovery) is complete — all outputs are in `migration-analysis/`. Check `migration-analysis/gate-check-report.md` for the gate status.                                             
                                                                                                                                                                                                                                                                           
  I've reviewed the migration report and approve moving to Phase 1 (Foundation). The two critical blockers (distutils in setup.py, pycrypto abandonment) should be addressed as prep work.                                                                                   
                                                                                                                                                                                                                                                                             
  For Phase 1, please:                                                                                                                                                                                                                                                       

  1. Run **py2to3-build-system-updater** to replace distutils with setuptools in setup.py and update requirements.txt (pycrypto→pycryptodome, version bumps for lxml, pyserial, SQLAlchemy).

  2. Run **py2to3-future-imports-injector** to add `from __future__ import print_function, division, absolute_import, unicode_literals` to all .py files.

  3. Run **py2to3-test-scaffold-generator** to create characterization tests for the 20 untested source modules, prioritizing the high/critical-risk ones (storage/database.py, automation/plugin_loader.py, io_protocols/serial_sensor.py, io_protocols/mqtt_listener.py).

  4. Run **py2to3-conversion-unit-planner** to finalize the conversion unit groupings and scheduling from the Phase 0 dependency graph.

  5. Run **py2to3-custom-lint-rules** to generate phase-specific linting that enforces the Phase 1 gate criteria.

  After each skill, update the migration state tracker. Then run the gate checker for Phase 1→2 readiness.

  Don't move past Phase 1 without my approval.
