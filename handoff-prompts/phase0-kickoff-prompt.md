I need to migrate this Python 2 codebase to Python 3. You have a suite of py2to3 migration skills installed — 26 skills across 6 phases that handle everything from initial analysis through final cutover.

Before we start writing any code, let's run Phase 0 (Discovery) to understand what we're working with. Please:

1. Run the **py2to3-codebase-analyzer** to scan the repo, build a dependency graph, and produce a migration readiness report. Pay attention to the risk scores — I want to know which modules are highest-risk before we touch anything.

2. Run the **py2to3-data-format-analyzer** to map bytes/string boundaries, binary protocols, and encoding hotspots. This is critical — the data layer is where most Py2→3 migrations break.

3. Run the **py2to3-serialization-detector** to find pickle, marshal, shelve, and any custom serialization that will break across interpreter versions.

4. Run the **py2to3-c-extension-flagger** if there are any C extensions, Cython, or ctypes usage.

5. Run the **py2to3-lint-baseline-generator** to capture our current lint state.

Our target Python version is 3.12. After each skill, save the outputs — we'll feed them into later phases.

Once Phase 0 is complete, use the **py2to3-migration-state-tracker** to initialize the migration state from the Phase 0 outputs. Then let's review what the **py2to3-gate-checker** says about our readiness to proceed to Phase 1.

Don't move past Phase 0 without my approval.

When finished, write a handoff prompt like this one that I can use to start the next phase in a new chat. It should summarize what was accomplished, reference the key output files, call out risks or blockers discovered, and list the specific skills and steps for the next phase. The goal is that someone starting a fresh session with only that prompt has full context to continue the migration.
