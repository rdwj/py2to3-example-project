# Py2-to-3 Custom Lint Rules Documentation

This document describes the custom pylint and flake8 rules created for the
Legacy Industrial Data Platform migration from Python 2.7 to Python 3.12.

The rules are organized into four progressive phases. Each phase includes all
rules from previous phases plus new ones, forming a ratchet that prevents
regressions as the migration advances.

## Quick Reference

| Phase | pylint Config                        | Rules Active                        |
|-------|--------------------------------------|-------------------------------------|
| 1     | `.lint-plugins/pylintrc-phase1`      | W9001, W9009, W9012                 |
| 2     | `.lint-plugins/pylintrc-phase2`      | Phase 1 + W9002-W9005, W9007-W9008, W9011, W9018, E950-E953 |
| 3     | `.lint-plugins/pylintrc-phase3`      | Phase 2 + W9006, W9010, W9013       |
| 4     | `.lint-plugins/pylintrc-phase4`      | Phase 3 + syntax-error, import-error |

## Usage

Run pylint with the phase-appropriate config:

```bash
# Phase 1 (current)
PYTHONPATH=".lint-plugins:$PYTHONPATH" \
  pylint --rcfile=.lint-plugins/pylintrc-phase1 \
         --load-plugins=py2_idioms_checker \
         src/ tests/

# Phase 2 (after Phase 1 gate passes)
PYTHONPATH=".lint-plugins:$PYTHONPATH" \
  pylint --rcfile=.lint-plugins/pylintrc-phase2 \
         --load-plugins=py2_idioms_checker \
         src/ tests/
```

Run flake8 data-layer checks (phases 2+):

```bash
PYTHONPATH=".lint-plugins:$PYTHONPATH" \
  flake8 --select=E950,E951,E952,E953 src/io_protocols/ src/data_processing/ src/storage/
```

Use pre-commit for automated enforcement:

```bash
pip install pre-commit
pre-commit install

# Set the migration phase (default: phase1)
export MIGRATION_PHASE=phase1
pre-commit run --all-files
```

---

## Phase 1 Rules

Phase 1 establishes the foundation for the migration. These rules must pass
before any code changes begin.

### W9001 / PY2001 -- Missing `__future__` imports

**What it detects:** Python files missing one or more of the four standard
`__future__` imports.

**Why it matters:** The `__future__` imports activate Python 3 behaviour in
Python 2, enabling dual-version compatibility during the migration. Without
them, code will behave differently between Python 2 and 3 (integer division,
print syntax, relative imports, string literals).

**How to fix:**

Add this line at the top of every `.py` file (after any module docstring):

```python
from __future__ import absolute_import, division, print_function, unicode_literals
```

**Affected files:** All 45 `.py` files.

---

### W9009 / PY2009 -- Py2-only stdlib import

**What it detects:** Imports of standard library modules that were removed
or renamed in Python 3.

**Why it matters:** These imports will raise `ImportError` under Python 3.
Identifying them early allows planning for the replacement.

**Detected modules and their replacements:**

| Python 2 Module   | Python 3 Replacement         |
|--------------------|------------------------------|
| `cPickle`          | `pickle`                     |
| `cStringIO`        | `io` (StringIO/BytesIO)      |
| `StringIO`         | `io.StringIO`                |
| `ConfigParser`     | `configparser`               |
| `Queue`            | `queue`                      |
| `thread`           | `threading` or `_thread`     |
| `commands`         | `subprocess`                 |
| `__builtin__`      | `builtins`                   |
| `copy_reg`         | `copyreg`                    |
| `repr`             | `reprlib`                    |
| `httplib`          | `http.client`                |
| `urllib2`          | `urllib.request`             |
| `xmlrpclib`        | `xmlrpc.client`              |
| `BaseHTTPServer`   | `http.server`                |
| `Cookie`           | `http.cookies`               |
| `cookielib`        | `http.cookiejar`             |
| `imp`              | `importlib`                  |
| `md5`              | `hashlib`                    |
| `sha`              | `hashlib`                    |
| `sets`             | builtin `set`                |

**How to fix:** Replace the import with the Python 3 equivalent. For example:

```python
# Before
import cPickle as pickle
from cStringIO import StringIO

# After
import pickle
from io import StringIO  # or BytesIO for binary data
```

**Affected files:** 18 files, 45 total occurrences.

---

### W9012 / PY2012 -- Implicit relative import

**What it detects:** `from X import ...` statements where `X` is a sibling
module in the same package but has no leading dot.

**Why it matters:** Python 3 removed implicit relative imports. Without a
leading dot, Python 3 will search `sys.path` instead of the current package,
likely raising `ImportError` or importing the wrong module.

**How to fix:**

```python
# Before (in src/core/__init__.py)
from exceptions import PlatformError

# After
from .exceptions import PlatformError
```

**Affected files:** 18 files, 49 total occurrences.

---

## Phase 2 Rules

Phase 2 targets the most common syntax and semantic changes. These are
largely mechanical transforms.

### W9002 / PY2002 -- Print statement

**What it detects:** `print` used as a statement (not a function call).

**Why it matters:** The print statement was removed in Python 3. It is a
`SyntaxError` without `from __future__ import print_function`.

**How to fix:**

```python
# Before
print "Hello, world"
print "Error:", msg
print >>sys.stderr, "Warning"

# After
print("Hello, world")
print("Error:", msg)
print("Warning", file=sys.stderr)
```

**Affected files:** 27 files, 188 total occurrences (185 print statements + 3 print chevron).

---

### W9003 / PY2003 -- Except comma syntax

**What it detects:** `except ExceptionType, variable:` using a comma instead
of `as`.

**Why it matters:** The comma syntax was removed in Python 3. It is also
ambiguous (does the comma introduce a variable or a second exception type?).

**How to fix:**

```python
# Before
except ValueError, e:

# After
except ValueError as e:
```

**Affected files:** 16 files, 66 total occurrences.

---

### W9004 / PY2004 -- xrange()

**What it detects:** Calls to `xrange()`.

**Why it matters:** `xrange()` was removed in Python 3. Python 3's `range()`
is lazy (equivalent to Py2's `xrange()`).

**How to fix:** Replace `xrange(...)` with `range(...)`.

**Affected files:** 7 files, 14 total occurrences.

---

### W9005 / PY2005 -- dict.iteritems/iterkeys/itervalues

**What it detects:** Calls to `.iteritems()`, `.iterkeys()`, or
`.itervalues()` on dict objects.

**Why it matters:** These methods were removed in Python 3. The standard
`.items()`, `.keys()`, `.values()` return views (lazy iterables) in Python 3.

**How to fix:** Replace `.iteritems()` with `.items()`, etc.

**Affected files:** 11 files, 27 total occurrences (23 iteritems + 4 viewkeys).

---

### W9007 / PY2007 -- dict.has_key()

**What it detects:** Calls to `.has_key()` on dict objects.

**Why it matters:** `dict.has_key()` was removed in Python 3.

**How to fix:**

```python
# Before
if d.has_key(k):

# After
if k in d:
```

**Affected files:** 9 files, 20 total occurrences.

---

### W9008 / PY2008a -- long type

**What it detects:** References to the `long` name as a type or function.

**Why it matters:** Python 3 unified `int` and `long` into a single `int`
type with arbitrary precision. `long` is a `NameError` in Python 3.

**How to fix:**

```python
# Before
isinstance(x, (int, long))
y = long(x)

# After
isinstance(x, int)
y = int(x)
```

**Affected files:** 5 files, 29 total occurrences.

---

### W9018 / PY2008b -- Long literal (L suffix)

**What it detects:** Integer literals with the `L` or `l` suffix (e.g., `123L`).

**Why it matters:** The `L` suffix is a `SyntaxError` in Python 3.

**How to fix:** Remove the `L` suffix. Python 3 `int` handles arbitrary
precision automatically.

```python
# Before
MAX_SIZE = 1073741824L

# After
MAX_SIZE = 1073741824
```

**Affected files:** 5 files, 40 total occurrences.

---

### W9011 / PY2011 -- file() builtin

**What it detects:** Calls to `file()` as a constructor.

**Why it matters:** The `file()` builtin was removed in Python 3.

**How to fix:** Replace `file(path, mode)` with `open(path, mode)`.

**Affected files:** 3 files, 10 total occurrences.

---

## Phase 2 Flake8 Rules

These rules focus on data-layer issues specific to the binary protocol and
serialization code.

### E950 -- Missing explicit binary mode in file open

**What it detects:** `open()` or `file()` calls in modules that import
`struct` or `socket` without an explicit mode argument, or opened in text
mode.

**Why it matters:** Binary protocol modules must use binary mode ('rb'/'wb')
to avoid implicit encoding/decoding in Python 3.

**How to fix:** Add explicit `'rb'` or `'wb'` mode argument.

---

### E951 -- Pickle without explicit protocol

**What it detects:** `pickle.dump()` or `pickle.dumps()` calls without a
`protocol` argument.

**Why it matters:** The default pickle protocol differs between Python 2
(protocol 0) and Python 3 (protocol 3+). During migration, you must choose
protocol 2 for cross-version compatibility or explicitly use
`pickle.HIGHEST_PROTOCOL` for Py3-only.

**How to fix:**

```python
# Cross-version compatible
pickle.dump(obj, f, protocol=2)

# Python 3 only (best performance)
pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
```

---

### E952 -- String/bytes concatenation

**What it detects:** String literals concatenated with expressions that return
bytes (`struct.pack()`, `recv()`, etc.), or string variables used as binary
accumulators (e.g., `out = ""`  followed by `out += struct.pack(...)`).

**Why it matters:** In Python 3, concatenating `str` with `bytes` raises
`TypeError`. This is the most common cause of runtime crashes in migrated
binary protocol code.

**How to fix:**

```python
# Before
out = ""
out += struct.pack("B", value)
vh = struct.pack(">H", 4) + "MQTT"

# After
out = b""
out += struct.pack("B", value)
vh = struct.pack(">H", 4) + b"MQTT"
```

---

### E953 -- Socket recv() without bytes handling

**What it detects:** `sock.recv()` results assigned to a variable without
subsequent `.decode()`, `bytes()`, or `struct.unpack()` calls on that variable
within the next few lines.

**Why it matters:** `socket.recv()` returns `bytes` in Python 3 but `str` in
Python 2. Code that treats the result as `str` (e.g., string concatenation,
`ord()` calls) will break.

**How to fix:**

For text protocols, decode immediately:

```python
data = sock.recv(1024).decode('utf-8')
```

For binary protocols, keep as bytes and use bytes operations:

```python
data = sock.recv(1024)  # bytes
value = data[0]  # int in Py3, no ord() needed
```

---

## Phase 3 Rules

Phase 3 targets the deeper semantic changes around string types and bytes
handling.

### W9006 / PY2006 -- basestring / unicode type

**What it detects:** References to `basestring` or `unicode` names.

**Why it matters:** Python 3 removed both names. `str` in Python 3 is always
Unicode (equivalent to Py2's `unicode`). `basestring` has no direct
equivalent.

**How to fix:**

```python
# Before
isinstance(x, basestring)    # "any string type"
isinstance(x, unicode)       # "is unicode text?"
text = unicode(raw, 'utf-8')

# After
isinstance(x, str)           # str is always text in Py3
isinstance(x, str)           # same -- str is unicode in Py3
text = raw.decode('utf-8')   # or str(raw, 'utf-8')
```

For cases where you need to accept both text and binary:

```python
isinstance(x, (str, bytes))
```

**Affected files:** 12 files, 66 total occurrences (12 basestring + 54 unicode).

---

### W9010 / PY2010 -- buffer() builtin

**What it detects:** Calls to `buffer()`.

**Why it matters:** `buffer()` was removed in Python 3 and replaced by
`memoryview()`.

**How to fix:**

```python
# Before
view = buffer(data, offset, length)

# After
view = memoryview(data)[offset:offset + length]
```

Note that `memoryview` slicing syntax differs from `buffer()` positional
arguments.

**Affected files:** 2 files, 2 total occurrences.

---

### W9013 / PY2013 -- ord() on bytes

**What it detects:** All `ord()` calls (requires human review to determine
which are actually on bytes data).

**Why it matters:** In Python 2, indexing a `str` (which is bytes) returns
a single-character string, requiring `ord()` to get the integer value.
In Python 3, indexing a `bytes` object returns an `int` directly, making
`ord()` redundant. Calling `ord()` on an `int` raises `TypeError`.

**How to fix:**

```python
# Before
byte_val = ord(data[0])
checksum ^= ord(c)

# After
byte_val = data[0]    # bytes[i] returns int in Py3
checksum ^= c         # iterating bytes yields int in Py3
```

**Affected files:** 5 files, 14 total occurrences.

---

## Phase 4 Rules

Phase 4 enables all custom rules plus standard pylint checks (`syntax-error`,
`import-error`) to validate that the migrated code actually parses and imports
correctly under Python 3. This is the final gate before declaring the
migration complete.

No new custom rules are added in Phase 4. The additional standard pylint
checks will catch:

- Syntax constructs that are illegal in Python 3 (backtick repr, `<>` operator, old octal literals)
- Import statements that fail because modules have been renamed/removed
- Any other parse errors introduced during the migration

---

## Coverage Analysis

The 17 custom lint rules cover 590 of the 699 Py2-isms identified in the
inventory (84.4%). The remaining 109 issues fall into 37 categories that
require manual code review because they involve:

- Semantic protocol changes (`__cmp__`, `__nonzero__`, `__div__`)
- Context-dependent decisions (integer division `/` vs `//`)
- Complex refactoring (tuple parameter unpacking, `imp` module migration)
- Low-count issues where a custom lint rule would be over-engineering

See `lint-rules-report.json` for the complete mapping of rules to inventory
categories and the list of uncovered categories.

---

## Pre-commit Integration

The `.pre-commit-config.yaml` at the project root integrates both linters
into the git workflow. The `MIGRATION_PHASE` environment variable controls
which phase's rules are enforced.

To advance to the next phase:

```bash
export MIGRATION_PHASE=phase2
pre-commit run --all-files
```

All violations must be resolved before the phase gate check passes.
