#!/bin/bash
# Run phase-specific lint checks for Py2→Py3 migration
set -e

PHASE="${1:-1}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Running Phase ${PHASE} lint checks..."

case $PHASE in
  1)
    echo "Phase 1: Foundation checks"
    python3 -c "
import ast, sys, os
# Check all .py files for __future__ imports
missing = []
for root, dirs, files in os.walk('${PROJECT_ROOT}/src'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path) as fh:
                content = fh.read()
            if 'from __future__ import' not in content:
                missing.append(os.path.relpath(path, '${PROJECT_ROOT}'))
for root, dirs, files in os.walk('${PROJECT_ROOT}/tests'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path) as fh:
                content = fh.read()
            if 'from __future__ import' not in content:
                missing.append(os.path.relpath(path, '${PROJECT_ROOT}'))
if missing:
    print('FAIL: Files missing __future__ imports:')
    for m in missing:
        print(f'  - {m}')
    sys.exit(1)
else:
    print('PASS: All files have __future__ imports')
"
    # Check no distutils
    if grep -r 'from distutils' "${PROJECT_ROOT}/setup.py" "${PROJECT_ROOT}/src/" 2>/dev/null; then
      echo "FAIL: distutils imports found"
      exit 1
    else
      echo "PASS: No distutils imports"
    fi
    # Check shebangs
    python3 -c "
import os, sys
bad = []
for d in ['${PROJECT_ROOT}/scripts']:
    if not os.path.exists(d):
        continue
    for f in os.listdir(d):
        if f.endswith('.py'):
            path = os.path.join(d, f)
            with open(path) as fh:
                first = fh.readline()
            if first.startswith('#!') and 'python' in first and 'python3' not in first:
                bad.append(os.path.relpath(path, '${PROJECT_ROOT}'))
if bad:
    print('FAIL: Scripts with non-python3 shebangs:')
    for b in bad:
        print(f'  - {b}')
    sys.exit(1)
else:
    print('PASS: All shebangs reference python3')
"
    # Check pycrypto not in requirements
    if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
      if grep -q 'pycrypto' "${PROJECT_ROOT}/requirements.txt" && ! grep -q 'pycryptodome' "${PROJECT_ROOT}/requirements.txt"; then
        echo "FAIL: pycrypto still in requirements.txt (use pycryptodome)"
        exit 1
      else
        echo "PASS: No pycrypto in requirements.txt"
      fi
    else
      echo "SKIP: No requirements.txt found"
    fi
    echo "Phase 1 checks complete!"
    ;;
  2)
    echo "Phase 2: Mechanical conversion checks"
    echo "Running flake8 with Phase 2 checker..."
    python3 -m flake8 "${PROJECT_ROOT}/src/" "${PROJECT_ROOT}/tests/" "${PROJECT_ROOT}/scripts/" \
      --select=PY2010,PY2011,PY2012,PY2013,PY2014,PY2015,PY2016,PY2017,PY2018,PY2019,PY2020,PY2021,PY2022,PY2023,PY2024,PY2025 \
      --max-line-length=120 || true
    echo ""
    echo "Summary by rule code:"
    python3 -m flake8 "${PROJECT_ROOT}/src/" "${PROJECT_ROOT}/tests/" "${PROJECT_ROOT}/scripts/" \
      --select=PY2010,PY2011,PY2012,PY2013,PY2014,PY2015,PY2016,PY2017,PY2018,PY2019,PY2020,PY2021,PY2022,PY2023,PY2024,PY2025 \
      --max-line-length=120 2>&1 | cut -d: -f4 | cut -d' ' -f2 | sort | uniq -c | sort -rn || true
    echo ""
    TOTAL=$(python3 -m flake8 "${PROJECT_ROOT}/src/" "${PROJECT_ROOT}/tests/" "${PROJECT_ROOT}/scripts/" \
      --select=PY2010,PY2011,PY2012,PY2013,PY2014,PY2015,PY2016,PY2017,PY2018,PY2019,PY2020,PY2021,PY2022,PY2023,PY2024,PY2025 \
      --max-line-length=120 2>&1 | wc -l | xargs)
    echo "Total findings: $TOTAL"
    echo "Phase 2 checks complete (findings are expected at this stage)."
    ;;
  *)
    echo "Unknown phase: $PHASE"
    exit 1
    ;;
esac
