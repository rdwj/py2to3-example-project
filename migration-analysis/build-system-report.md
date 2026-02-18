# Build System Migration Report

**Skill:** py2to3-build-system-updater
**Target Version:** Python 3.12
**Generated:** 2026-02-18T14:25:51Z

## Executive Summary

Successfully updated the build system and dependencies for Python 3.12 compatibility. All files have been migrated from deprecated distutils to setuptools, dependency versions have been updated to Python 3.12-compatible releases, and script shebangs have been updated to use python3.

**Status:** Ready for Phase 2 syntax conversion

## Files Modified

1. `setup.py` - Build system configuration
2. `requirements.txt` - Dependency specifications
3. `scripts/run_platform.py` - Main platform entry point
4. `scripts/batch_import.py` - Mainframe batch import script
5. `scripts/sensor_monitor.py` - IoT sensor monitoring daemon

## Critical Changes

### setup.py Migration (distutils → setuptools)

**Before:**
```python
from distutils.core import setup
```

**After:**
```python
from setuptools import setup, find_packages
```

**Key Updates:**

- Replaced deprecated `distutils.core.setup` with `setuptools.setup`
- Added `python_requires='>=3.12'` to enforce minimum Python version
- Added `install_requires` that reads from `requirements.txt` dynamically
- Added comprehensive classifiers for Python 3.12 support
- Updated shebang from `#!/usr/bin/env python` to `#!/usr/bin/env python3`
- Kept explicit package list (not using find_packages() yet) to maintain existing structure

### requirements.txt Dependency Updates

All dependencies updated to Python 3.12-compatible versions with `>=` constraints for migration flexibility:

| Package | Old Version | New Version | Severity | Notes |
|---------|-------------|-------------|----------|-------|
| pyserial | 2.7 | >=3.5 | Low | Standard upgrade for Py3 |
| paho-mqtt | 1.3.1 | >=1.6.1 | Low | Standard upgrade for Py3 |
| **pymodbus** | 1.3.2 | >=3.6.0 | **HIGH** | Major API changes (1.x → 3.x) |
| lxml | 3.8.0 | >=5.1.0 | Low | Modern XML processing |
| opcua | 0.98.6 | >=0.98.13 | Low | Consider asyncua migration |
| **SQLAlchemy** | 0.9.9 | >=2.0.0 | **HIGH** | Major API changes (0.9 → 2.0) |
| simplejson | 3.8.2 | >=3.19.0 | Low | Standard upgrade |
| Jinja2 | 2.7.3 | >=3.1.0 | Medium | Stricter autoescape behavior |
| MarkupSafe | 0.23 | >=2.1.0 | Low | Required by Jinja2 |
| chardet | 2.3.0 | >=5.2.0 | Low | Standard upgrade |
| **pycrypto** | 2.6.1 | **pycryptodome>=3.20.0** | **HIGH** | Abandoned library replaced |
| requests | 2.5.3 | >=2.31.0 | Low | Security fixes included |
| six | 1.9.0 | >=1.16.0 | Low | Kept for migration phase |

### Script Shebangs Updated

All three scripts updated:

- `scripts/run_platform.py`: `#!/usr/bin/env python` → `#!/usr/bin/env python3`
- `scripts/batch_import.py`: `#!/usr/bin/env python` → `#!/usr/bin/env python3`
- `scripts/sensor_monitor.py`: `#!/usr/bin/env python` → `#!/usr/bin/env python3`

## High-Impact Dependency Changes

### 1. pymodbus (1.3.2 → 3.6.0) - HIGH SEVERITY

**Impact:**
- Major API breaking changes in client initialization
- Register reading methods have new signatures
- Error handling patterns changed
- Transaction management updated

**Action Required:**
- Review `src/io_protocols/modbus_client.py` during Phase 2 syntax conversion
- Update all pymodbus API calls to 3.x syntax
- Test Modbus communication thoroughly after migration

**Example API Changes:**
```python
# Old (1.x)
client = ModbusClient(host='localhost', port=502)
client.connect()
result = client.read_holding_registers(0, 10)

# New (3.x)
from pymodbus.client import ModbusTcpClient
client = ModbusTcpClient('localhost', port=502)
client.connect()
result = client.read_holding_registers(address=0, count=10)
```

### 2. SQLAlchemy (0.9.9 → 2.0.0) - HIGH SEVERITY

**Impact:**
- Query API completely redesigned
- Session management patterns changed
- Declarative base initialization updated
- Relationship and backref syntax modernized

**Action Required:**
- Review `src/storage/database.py` during Phase 2 syntax conversion
- Migrate all queries from 0.9 → 2.0 API
- Update session management code
- Test all database operations after migration

**Example API Changes:**
```python
# Old (0.9)
session.query(User).filter_by(name='john').first()

# New (2.0)
from sqlalchemy import select
session.execute(select(User).where(User.name == 'john')).scalar_one_or_none()
```

### 3. pycrypto → pycryptodome (CRITICAL REPLACEMENT)

**Impact:**
- pycrypto is abandoned and has known security vulnerabilities
- pycryptodome is a drop-in replacement fork with active maintenance
- API should be mostly compatible, but verification needed

**Action Required:**
- Test all encryption/decryption operations in `src/data_processing/legacy_crypto.py`
- Verify AES, DES, and RSA usage after upgrade
- Check for any deprecated cipher modes

**Import Changes:**
```python
# Both use the same imports (drop-in replacement)
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
# Should work unchanged with pycryptodome
```

## Medium-Impact Dependency Changes

### Jinja2 (2.7.3 → 3.1.0)

**Impact:**
- Stricter autoescape behavior for security
- Updated template syntax and filters
- May affect template rendering in `src/reporting/report_generator.py`

**Action Required:**
- Review and test all Jinja2 templates
- Check for any deprecated filters or template syntax

### lxml (3.8.0 → 5.1.0)

**Impact:**
- Performance improvements
- Updated XML parsing API
- May affect `src/data_processing/xml_parser.py`

**Action Required:**
- Test all XML parsing operations
- Verify XPath expressions still work correctly

## MANIFEST.in Status

**File:** MANIFEST.in
**Status:** OK - No changes required

The existing MANIFEST.in includes all necessary patterns for Python 3 build system:
- Includes README.txt, requirements.txt, setup.py
- Recursively includes config files (*.ini, *.conf)
- Recursively includes data files (*.dat, *.csv, *.xml, *.json)
- Recursively includes all Python files in scripts/, src/, and tests/

## Validation Checklist

Before proceeding to Phase 2:

- [x] setup.py migrated from distutils to setuptools
- [x] python_requires='>=3.12' added to setup.py
- [x] install_requires reads from requirements.txt
- [x] All dependencies updated to Python 3.12-compatible versions
- [x] Script shebangs updated to python3
- [x] Classifiers updated for Python 3.12 support
- [x] MANIFEST.in reviewed and confirmed compatible

After Phase 2 (Syntax Conversion):

- [ ] Install dependencies in Python 3.12 venv
- [ ] Test pymodbus API migration
- [ ] Test SQLAlchemy API migration
- [ ] Verify pycryptodome crypto operations
- [ ] Test Jinja2 template rendering
- [ ] Test lxml XML parsing
- [ ] Run full test suite with new dependencies

## Next Steps

1. **Immediate (Phase 1 completion):**
   - Run `py2to3-future-imports-injector` to add `__future__` imports to all .py files
   - Run gate checker to validate Phase 1 completion criteria

2. **Phase 2 (Syntax Conversion):**
   - Convert all Python 2 syntax to Python 3 (print statements, exceptions, etc.)
   - Update pymodbus API calls in `src/io_protocols/modbus_client.py`
   - Update SQLAlchemy queries in `src/storage/database.py`
   - Test all modified code

3. **Phase 3 (Dependency Testing):**
   - Create Python 3.12 virtual environment
   - Install updated dependencies: `pip install -r requirements.txt`
   - Run test suite against new dependency versions
   - Address any API incompatibilities

4. **Phase 4 (six Removal):**
   - Remove `six` compatibility layer after all Python 2 syntax is converted
   - Update requirements.txt to remove six
   - Clean up any remaining Python 2/3 compatibility shims

## Migration Status

**Current Phase:** 1 (Build System Update)
**Gate Status:** build_system_updated ✓
**Ready for Phase 2:** Yes
**Blockers:** None

## Recommendations

1. **Test Environment Setup:** Create a Python 3.12 virtual environment immediately after Phase 2 to validate dependency compatibility early.

2. **API Migration Priority:** Focus on pymodbus and SQLAlchemy API migration during Phase 2 syntax conversion, as these are the highest-risk changes.

3. **Incremental Testing:** Test each major dependency update independently rather than all at once to isolate any compatibility issues.

4. **Consider asyncua:** After completing the migration, evaluate migrating from `opcua` to `asyncua` for better Python 3 async/await support in the OPC UA client.

5. **Security Audit:** The pycryptodome upgrade addresses known security vulnerabilities in pycrypto. Consider a full cryptographic audit after migration to ensure best practices.

## Summary of Changes by Type

| Change Type | Count | Files Affected |
|-------------|-------|----------------|
| Critical Fix | 3 | setup.py, requirements.txt |
| Dependency Upgrade | 13 | requirements.txt |
| Interpreter Directive | 4 | setup.py, scripts/*.py |
| Version Constraint | 1 | setup.py |
| Dependency Management | 1 | setup.py |
| Metadata | 1 | setup.py |

**Total Changes:** 23 across 5 files

---

**Report Generated By:** py2to3-build-system-updater skill
**Project:** legacy-industrial-platform
**Target:** Python 3.12
