# Build System Update Report

**Date:** 2026-02-12
**Target Python:** 3.12
**Status:** Changes applied

## Summary

Two critical blockers have been resolved:

1. **distutils removed in Python 3.12** -- `setup.py` migrated from `distutils.core` to `setuptools`.
2. **pycrypto abandoned** -- Replaced with `pycryptodome` in `requirements.txt`.

All 13 dependency version pins have been updated for Python 3.12 compatibility. The `six` compatibility library has been removed since it serves no purpose in a Python 3-only codebase.

## Files Modified

| File | Change |
|------|--------|
| `setup.py` | distutils -> setuptools, added `python_requires`, classifiers, shebang |
| `requirements.txt` | All 13 packages updated; pycrypto replaced; six removed |
| `scripts/run_platform.py` | Shebang `python` -> `python3` |
| `scripts/batch_import.py` | Shebang `python` -> `python3` |
| `scripts/sensor_monitor.py` | Shebang `python` -> `python3` |

## setup.py Changes

The import was changed from:

```python
from distutils.core import setup
```

to:

```python
from setuptools import setup, find_packages
```

Additional metadata added:

- `python_requires=">=3.12"` -- prevents installation under older Python versions
- Classifiers for Python 3.12 (removed implicit Python 2 assumption)
- Shebang updated to `#!/usr/bin/env python3`

All existing metadata (name, version, packages, scripts, data_files) was preserved unchanged.

## Dependency Updates

### Critical (blockers resolved)

| Package | Old | New | Notes |
|---------|-----|-----|-------|
| pycrypto | ==2.6.1 | **pycryptodome>=3.20.0** | Abandoned, no Py3 support. Drop-in fork. |

### Medium Risk (API changes possible)

| Package | Old | New | Notes |
|---------|-----|-----|-------|
| pymodbus | ==1.3.2 | >=3.6.0 | **Major API changes** in 3.x. Source code updates required. |
| SQLAlchemy | ==0.9.9 | >=1.4.54 | EOL version. 1.4 is largely compatible. |
| lxml | ==3.8.0 | >=5.1.0 | C extension rebuild; API stable. |
| opcua | ==0.98.6 | >=0.98.13 | Limited maintenance; consider opcua-asyncio long term. |

### Low Risk (API stable)

| Package | Old | New | Notes |
|---------|-----|-----|-------|
| pyserial | ==2.7 | >=3.5 | API stable |
| paho-mqtt | ==1.3.1 | >=1.6.1 | Avoid 2.x (breaking callback API) |
| simplejson | ==3.8.2 | >=3.19.0 | API stable |
| Jinja2 | ==2.7.3 | >=3.1.0 | Some deprecated APIs removed |
| MarkupSafe | ==0.23 | >=2.1.0 | Required by Jinja2 3.x |
| chardet | ==2.3.0 | >=5.2.0 | API stable |
| requests | ==2.5.3 | >=2.31.0 | Security fixes; API stable |

### Removed

| Package | Old | Reason |
|---------|-----|--------|
| six | ==1.9.0 | Py2/3 compat library; unnecessary after migration |

## Shebang Updates

Four files had their shebangs updated from `#!/usr/bin/env python` to `#!/usr/bin/env python3`. The `scripts/generate_ebcdic_data.py` already had the correct shebang.

## Items Not Requiring Changes

- `create_structure.sh` -- No Python references
- `config/platform.ini` -- Application configuration, not build system
- `scripts/generate_ebcdic_data.py` -- Already Python 3

## Absent Build Infrastructure

The project currently lacks several modern Python build/CI files. These are not blockers for the migration but should be considered as follow-up improvements:

- `pyproject.toml` -- PEP 621 project metadata (modern replacement for setup.py)
- `setup.cfg` -- Declarative setuptools config
- `tox.ini` -- Multi-environment test runner
- `Makefile` -- Build automation
- `.pre-commit-config.yaml` -- Pre-commit hooks

## Follow-up Actions Required in Phase 1

1. **pymodbus API migration** -- `src/io_protocols/modbus_client.py` uses pymodbus 1.x APIs that changed significantly in 3.x. Client constructor, register read/write methods, and response handling all need updates.

2. **Remove six usage** -- Grep the codebase for `import six` and `from six` and replace with native Python 3 equivalents.

3. **pycryptodome API audit** -- Although no `Crypto.*` imports were found in the current source tree, any dynamically loaded plugins or configuration-driven imports should be verified against pycryptodome's API.

4. **paho-mqtt version guard** -- Consider adding an upper bound (`<2.0`) to the paho-mqtt requirement to prevent accidental installation of 2.x, which has breaking callback signature changes.
