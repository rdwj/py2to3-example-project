# Custom Lint Rules for Python 2→3 Migration

This document describes the custom lint rules created to enforce Phase 1 and Phase 2 migration gates for the py2to3-example-project targeting Python 3.12.

## Overview

Two custom flake8 plugins have been created:

- **Phase 1 Checker** (`.lint-plugins/flake8_phase1_checker.py`) - Foundation gate criteria
- **Phase 2 Checker** (`.lint-plugins/flake8_phase2_checker.py`) - Mechanical conversion patterns

These plugins detect Python 2 patterns and missing compatibility requirements that need to be addressed during migration.

## Phase 1 Rules: Foundation

Phase 1 rules enforce foundational compatibility requirements that allow code to run on both Python 2 and Python 3.

### PY2001: Missing __future__ imports

**Severity:** Error
**Automatable:** Yes

All Python files must include the four required `__future__` imports at the top:

```python
from __future__ import absolute_import, division, print_function, unicode_literals
```

**Bad:**
```python
# Missing __future__ imports
def foo():
    print "Hello"
```

**Good:**
```python
from __future__ import absolute_import, division, print_function, unicode_literals

def foo():
    print("Hello")
```

### PY2002: distutils import found

**Severity:** Error
**Automatable:** Yes

The deprecated `distutils` package must be replaced with `setuptools`.

**Bad:**
```python
from distutils.core import setup
```

**Good:**
```python
from setuptools import setup
```

### PY2003: Shebang references python not python3

**Severity:** Warning
**Automatable:** Yes

Script shebangs should explicitly reference `python3` instead of `python`.

**Bad:**
```bash
#!/usr/bin/env python
```

**Good:**
```bash
#!/usr/bin/env python3
```

## Phase 2 Rules: Mechanical Conversion

Phase 2 rules detect Python 2 syntax and builtin usage that must be mechanically converted to Python 3 equivalents.

### PY2010: print statement

**Severity:** Error
**Automatable:** Yes

Print statements must be converted to print function calls.

**Bad:**
```python
print "Hello, world"
print x, y, z
```

**Good:**
```python
print("Hello, world")
print(x, y, z)
```

### PY2011: print >> redirect syntax

**Severity:** Error
**Automatable:** Yes

Print redirection syntax must use the `file=` parameter.

**Bad:**
```python
print >>sys.stderr, "Error message"
```

**Good:**
```python
print("Error message", file=sys.stderr)
```

### PY2012: except comma syntax

**Severity:** Error
**Automatable:** Yes

Exception handling must use `as` keyword instead of comma.

**Bad:**
```python
try:
    something()
except Exception, e:
    handle(e)
```

**Good:**
```python
try:
    something()
except Exception as e:
    handle(e)
```

### PY2013: dict.has_key()

**Severity:** Error
**Automatable:** Yes

Dictionary `has_key()` method must be replaced with `in` operator.

**Bad:**
```python
if mydict.has_key('foo'):
    return mydict['foo']
```

**Good:**
```python
if 'foo' in mydict:
    return mydict['foo']
```

### PY2014: xrange()

**Severity:** Error
**Automatable:** Yes

`xrange()` must be replaced with `range()`.

**Bad:**
```python
for i in xrange(100):
    process(i)
```

**Good:**
```python
for i in range(100):
    process(i)
```

### PY2015: raw_input()

**Severity:** Error
**Automatable:** Yes

`raw_input()` must be replaced with `input()`.

**Bad:**
```python
name = raw_input("Enter name: ")
```

**Good:**
```python
name = input("Enter name: ")
```

### PY2016: execfile()

**Severity:** Error
**Automatable:** Yes

`execfile()` must be replaced with `exec(open(...).read())`.

**Bad:**
```python
execfile('script.py')
```

**Good:**
```python
exec(open('script.py').read())
```

### PY2017: basestring

**Severity:** Error
**Automatable:** Yes

`basestring` type must be replaced with `str`.

**Bad:**
```python
if isinstance(value, basestring):
    return value
```

**Good:**
```python
if isinstance(value, str):
    return value
```

### PY2018: unicode type

**Severity:** Error
**Automatable:** Yes

`unicode` type must be replaced with `str`.

**Bad:**
```python
text = unicode(data, 'utf-8')
```

**Good:**
```python
text = str(data, 'utf-8')
```

### PY2019: long type

**Severity:** Error
**Automatable:** Yes

`long` type must be replaced with `int`.

**Bad:**
```python
big_number = long(1234567890)
```

**Good:**
```python
big_number = int(1234567890)
```

### PY2020: dict.iter*()

**Severity:** Error
**Automatable:** Yes

Dictionary `iterkeys()`, `itervalues()`, and `iteritems()` methods must be replaced with `keys()`, `values()`, and `items()`.

**Bad:**
```python
for key in mydict.iterkeys():
    process(key)
for value in mydict.itervalues():
    process(value)
for k, v in mydict.iteritems():
    process(k, v)
```

**Good:**
```python
for key in mydict.keys():
    process(key)
for value in mydict.values():
    process(value)
for k, v in mydict.items():
    process(k, v)
```

### PY2021: dict.view*()

**Severity:** Error
**Automatable:** Yes

Dictionary `viewkeys()`, `viewvalues()`, and `viewitems()` methods must be replaced with `keys()`, `values()`, and `items()`.

**Bad:**
```python
keys_view = mydict.viewkeys()
```

**Good:**
```python
keys_view = mydict.keys()
```

### PY2022: old-style raise

**Severity:** Error
**Automatable:** Yes

Old-style raise syntax must be replaced with new-style.

**Bad:**
```python
raise ValueError, "Invalid value"
```

**Good:**
```python
raise ValueError("Invalid value")
```

### PY2023: <> operator

**Severity:** Error
**Automatable:** Yes

The `<>` operator must be replaced with `!=`.

**Bad:**
```python
if x <> y:
    do_something()
```

**Good:**
```python
if x != y:
    do_something()
```

### PY2024: backtick repr

**Severity:** Error
**Automatable:** Yes

Backtick repr syntax must be replaced with `repr()` function.

**Bad:**
```python
s = `obj`
```

**Good:**
```python
s = repr(obj)
```

### PY2025: old-style octal literal

**Severity:** Error
**Automatable:** Yes

Old-style octal literals must use `0o` prefix.

**Bad:**
```python
mode = 0644
```

**Good:**
```python
mode = 0o644
```

## Running Lint Checks

### Command Line

Use the provided shell script to run phase-specific checks:

```bash
# Run Phase 1 checks
bash scripts/run_lint.sh 1

# Run Phase 2 checks
bash scripts/run_lint.sh 2
```

### Phase 1 Execution

Phase 1 checks verify foundation requirements:

1. All `.py` files have required `__future__` imports
2. No `distutils` imports in setup.py or source code
3. Script shebangs reference `python3`
4. No `pycrypto` in requirements.txt (use `pycryptodome`)

Exit code 0 indicates all checks passed. Non-zero indicates failures.

### Phase 2 Execution

Phase 2 checks scan for Python 2 patterns using the custom flake8 plugin. The script outputs flake8 findings for all detected patterns.

Note: Phase 2 findings are expected before conversion work begins. The baseline finding count guides conversion efforts.

## CI Integration

To integrate these checks into CI/CD pipelines:

### GitHub Actions

```yaml
name: Migration Lint Checks

on: [push, pull_request]

jobs:
  phase1-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install flake8
      - name: Run Phase 1 checks
        run: bash scripts/run_lint.sh 1
      - name: Run Phase 2 baseline
        run: bash scripts/run_lint.sh 2
```

### Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Phase 1 Lint') {
            steps {
                sh 'bash scripts/run_lint.sh 1'
            }
        }
        stage('Phase 2 Baseline') {
            steps {
                sh 'bash scripts/run_lint.sh 2 | tee phase2-findings.txt'
            }
        }
    }
}
```

### GitLab CI

```yaml
lint:phase1:
  script:
    - bash scripts/run_lint.sh 1
  only:
    - merge_requests
    - main

lint:phase2:
  script:
    - bash scripts/run_lint.sh 2 | tee phase2-findings.txt
  artifacts:
    paths:
      - phase2-findings.txt
  only:
    - merge_requests
    - main
```

## Gate Enforcement

These lint rules enforce migration gates:

- **Phase 1 Gate:** All Phase 1 checks must pass (exit 0) before proceeding to Phase 2
- **Phase 2 Gate:** Phase 2 finding count must reach 0 before proceeding to Phase 3

The `py2to3-gate-checker` script uses these lint results along with other criteria to validate gate passage.

## Extending the Rules

To add new custom rules:

1. Edit the appropriate checker file in `.lint-plugins/`
2. Add a new method following the pattern `_check_<pattern_name>()`
3. Yield tuples: `(line_number, column_offset, "PY2XXX message", type(self))`
4. Add the check to the `run()` method
5. Document the new rule in this file
6. Update the rule count in `lint-rules-report.json`

## Files Created

- `.lint-plugins/flake8_phase1_checker.py` - Phase 1 flake8 plugin
- `.lint-plugins/flake8_phase2_checker.py` - Phase 2 flake8 plugin
- `.lint-plugins/__init__.py` - Python package marker
- `.lint-plugins/setup.cfg` - Flake8 configuration
- `scripts/run_lint.sh` - Lint execution script
- `migration-analysis/lint-rules-report.json` - Rules metadata
- `migration-analysis/lint-rules-documentation.md` - This file
