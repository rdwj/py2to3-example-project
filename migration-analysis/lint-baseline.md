# Lint Baseline Report: Python 2 to 3 Migration

**Scan date:** 2026-02-12
**Target version:** Python 3.12
**Baseline commit:** `c4c0165` (unmodified Python 2.7 codebase)
**Source data:** `py2-ism-inventory.json`

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total Python files | 45 |
| Files with issues | 39 |
| Clean files | 6 |
| Total lines of code | 8,074 |
| Total issues found | 699 |
| Issues per 100 lines | 8.66 |
| Unique issue categories | 59 (57 with discrete counts, 2 cross-cutting) |

### Severity Breakdown

| Severity | Count | Percentage | Description |
|---|---|---|---|
| Critical | 1 | 0.1% | distutils removal blocker for Python 3.12 |
| High | 529 | 75.7% | Syntax errors and semantic issues that prevent execution |
| Medium | 165 | 23.6% | Renamed builtins, removed dict methods, iterator changes |
| Low | 4 | 0.6% | Minor deprecations (intern, os.popen, xreadlines, InstanceType) |

Two additional cross-cutting concerns (DATA_ENCODING_BOUNDARY and DATA_STRUCT_MIXED) affect
the `io_protocols/`, `data_processing/`, and `storage/` packages but are not counted as
discrete occurrences. These require a separate manual audit of every I/O boundary.

---

## Per-Module Lint Scores

Sorted by issue density (worst first). Density = issues per 100 lines of code.

### Risk: Critical (density >= 15.0)

| File | Issues | Lines | Density | Top Categories |
|---|---|---|---|---|
| src/core/\_\_init\_\_.py | 3 | 8 | 37.5 | implicit relative imports |
| src/data\_processing/\_\_init\_\_.py | 6 | 17 | 35.3 | implicit relative imports |
| src/io\_protocols/\_\_init\_\_.py | 4 | 14 | 28.6 | implicit relative imports |
| src/automation/\_\_init\_\_.py | 3 | 12 | 25.0 | implicit relative imports |
| src/storage/\_\_init\_\_.py | 3 | 13 | 23.1 | implicit relative imports |
| src/reporting/\_\_init\_\_.py | 3 | 14 | 21.4 | implicit relative imports |
| src/reporting/report\_generator.py | 37 | 220 | 16.8 | unicode(11), print(5), except-comma(4), reduce(4) |

Note: The `__init__.py` files have inflated densities due to their small size (8-17 lines)
combined with 3-6 implicit relative imports each. The real concern among the critical files
is `report_generator.py`, which has 37 issues across multiple categories in substantive code.

### Risk: High (density 10.0 - 14.9)

| File | Issues | Lines | Density | Top Categories |
|---|---|---|---|---|
| src/storage/cache.py | 38 | 257 | 14.8 | long-literal(11), print(9), cPickle(3), iteritems(3) |
| src/automation/plugin\_loader.py | 39 | 264 | 14.8 | print(16), except-comma(5), method-attrs(4), func-attrs(3) |
| src/storage/database.py | 39 | 277 | 14.1 | print(14), except-comma(10), StandardError(6), cPickle(4) |
| tests/test\_mainframe\_parser.py | 18 | 141 | 12.8 | long-type(13), print(5) |
| src/data\_processing/mainframe\_parser.py | 55 | 438 | 12.6 | long-literal(17), print(9), long-type(7), file()(4) |
| src/core/string\_helpers.py | 22 | 178 | 12.4 | unicode(15), basestring(5), removed-stdlib(2) |
| src/io\_protocols/modbus\_client.py | 27 | 220 | 12.3 | print(7), ord-on-bytes(6), except-comma(5), int-div(3) |
| src/core/compat.py | 13 | 107 | 12.1 | unicode(7), removed-stdlib(5), long-type(1) |
| src/automation/script\_runner.py | 25 | 207 | 12.1 | print(10), operator-removed(3), iteritems(3) |
| tests/test\_core\_types.py | 15 | 127 | 11.8 | cmp(5), print(5), long-type(3), basestring(2) |
| tests/conftest.py | 6 | 56 | 10.7 | print(2), unicode(2), hex-decode(2) |
| src/storage/file\_store.py | 25 | 239 | 10.5 | print(9), file()(6), unicode(4), octal(3) |
| src/automation/scheduler.py | 29 | 287 | 10.1 | print(14), except-comma(2), iteritems(2), xrange(2) |

### Risk: Medium (density 5.0 - 9.9)

| File | Issues | Lines | Density | Top Categories |
|---|---|---|---|---|
| src/io\_protocols/opcua\_client.py | 24 | 251 | 9.6 | except-comma(9), print(6), removed-stdlib(6), has\_key(3) |
| src/io\_protocols/mqtt\_listener.py | 27 | 281 | 9.6 | print(9), except-comma(4), xrange(3), ord-on-bytes(3) |
| src/io\_protocols/serial\_sensor.py | 17 | 182 | 9.3 | print(7), ord-on-bytes(3), iteritems(2), next()(2) |
| src/core/config\_loader.py | 18 | 196 | 9.2 | print(15), removed-stdlib(2), sys.maxint(1) |
| src/core/types.py | 21 | 231 | 9.1 | long-literal(7), long-type(5), cmp(3) |
| src/reporting/email\_sender.py | 15 | 180 | 8.3 | print(6), except-comma(3), unicode(3), imports(3) |
| src/reporting/web\_dashboard.py | 22 | 277 | 7.9 | print(11), removed-stdlib(5), iteritems(3) |
| src/core/exceptions.py | 12 | 169 | 7.1 | except-comma(5), raise-two-arg(4), sys.exc\_attrs(3) |
| src/core/utils.py | 13 | 189 | 6.9 | xrange(2), has\_key(2), raw\_input(2), apply(2) |
| src/data\_processing/xml\_transformer.py | 20 | 307 | 6.5 | has\_key(5), print(5), unicode(3), imports(3) |
| src/data\_processing/json\_handler.py | 20 | 324 | 6.2 | json-encoding(5), has\_key(3), iteritems(2), unicode(2) |
| src/data\_processing/text\_analyzer.py | 18 | 296 | 6.1 | map/filter(4), imports(3), unicode(2), iteritems(2) |
| tests/test\_report\_generator.py | 8 | 139 | 5.8 | print(4), reduce(3), removed-stdlib(1) |
| src/core/itertools\_helpers.py | 14 | 246 | 5.7 | viewkeys(4), izip/imap(4), next()(3), iteritems(2) |

### Risk: Low (density < 5.0)

| File | Issues | Lines | Density | Top Categories |
|---|---|---|---|---|
| src/data\_processing/csv\_processor.py | 15 | 319 | 4.7 | unicode(4), print(3), imports(3), has\_key(2) |
| tests/test\_modbus.py | 5 | 118 | 4.2 | print(5) |
| tests/test\_csv\_processor.py | 4 | 114 | 3.5 | print(3), removed-stdlib(1) |
| src/data\_processing/log\_parser.py | 15 | 435 | 3.4 | print(6), except-comma(2), imports(2) |
| setup.py | 1 | 47 | 2.1 | IMPORT\_DISTUTILS (critical severity) |

### Clean Files (0 issues)

`src/__init__.py`, `tests/__init__.py`, `scripts/batch_import.py`,
`scripts/generate_ebcdic_data.py`, `scripts/run_platform.py`, `scripts/sensor_monitor.py`

---

## Category Breakdown

All 59 categories from the inventory, grouped by type.

### Syntax Issues (302 total, all automatable)

| Category | Count | Description |
|---|---|---|
| SYNTAX\_PRINT\_STATEMENT | 185 | `print x` without parentheses |
| SYNTAX\_EXCEPT\_COMMA | 66 | `except Type, e:` comma syntax |
| SYNTAX\_LONG\_LITERAL | 40 | `123L` long integer suffix |
| SYNTAX\_OCTAL\_LITERAL | 4 | `0755` old-style octal |
| SYNTAX\_RAISE\_TWO\_ARG | 4 | `raise Type, value` two-arg syntax |
| SYNTAX\_PRINT\_CHEVRON | 3 | `print >>file` redirect syntax |
| SYNTAX\_EXEC\_STATEMENT | 2 | `exec code` statement |
| SYNTAX\_EXECFILE | 1 | `execfile()` builtin |
| SYNTAX\_BACKTICK\_REPR | 1 | `` `obj` `` backtick repr |
| SYNTAX\_DIAMOND\_OPERATOR | 1 | `<>` inequality operator |

### Semantic / Type System Issues (249 total)

| Category | Count | Description |
|---|---|---|
| SEMANTIC\_UNICODE\_TYPE | 54 | `unicode()` and `isinstance(x, unicode)` |
| SEMANTIC\_IMPLICIT\_RELATIVE\_IMPORT | 49 | `from module import X` without leading dot |
| SEMANTIC\_LONG\_TYPE | 29 | `long()` and `isinstance(x, long)` |
| SEMANTIC\_DICT\_ITERITEMS | 23 | `.iteritems()`, `.iterkeys()`, `.itervalues()` |
| SEMANTIC\_DICT\_HAS\_KEY | 20 | `dict.has_key(k)` |
| SEMANTIC\_XRANGE | 14 | `xrange()` |
| SEMANTIC\_BASESTRING | 12 | `isinstance(x, basestring)` |
| SEMANTIC\_CPICKLE | 11 | `cPickle` module usage |
| SEMANTIC\_FILE\_BUILTIN | 10 | `file()` as constructor |
| SEMANTIC\_STANDARD\_ERROR | 8 | `StandardError` base class |
| SEMANTIC\_REDUCE | 8 | `reduce()` builtin (moved to functools) |
| SEMANTIC\_CMP | 8 | `__cmp__`, `cmp()`, `sorted(cmp=)` |
| SEMANTIC\_INTEGER\_DIVISION | 7 | `/` for integer division |
| SEMANTIC\_JSON\_ENCODING\_PARAM | 6 | `json.loads(encoding=)` removed parameter |
| SEMANTIC\_OPERATOR\_REMOVED | 5 | `operator.isCallable` etc. |
| SEMANTIC\_SYS\_EXC\_ATTRS | 5 | `sys.exc_type`, `sys.exc_value` |
| SEMANTIC\_ITERATOR\_NEXT | 5 | `obj.next()` instead of `next(obj)` |
| SEMANTIC\_ITERTOOLS\_IZIP | 4 | `itertools.izip`, `imap`, `ifilter` |
| SEMANTIC\_DICT\_VIEWKEYS | 4 | `.viewkeys()`, `.viewvalues()`, `.viewitems()` |
| SEMANTIC\_MAP\_FILTER\_LIST | 4 | `map()`/`filter()` expecting list |
| SEMANTIC\_METHOD\_ATTRS | 4 | `im_func`, `im_self`, `im_class` |
| SEMANTIC\_FUNC\_ATTRS | 3 | `func_name`, `func_defaults`, `func_closure` |
| SEMANTIC\_COMMANDS\_MODULE | 3 | `commands.getoutput()` |
| SEMANTIC\_APPLY | 2 | `apply(func, args)` |
| SEMANTIC\_BUFFER | 2 | `buffer()` builtin |
| SEMANTIC\_METACLASS\_ATTR | 2 | `__metaclass__` attribute |
| SEMANTIC\_TUPLE\_PARAM\_UNPACK | 2 | `def f((a, b)):` tuple unpacking |
| SEMANTIC\_RELOAD | 2 | `reload()` builtin |
| SEMANTIC\_IMP\_MODULE | 2 | `imp` module (deprecated) |
| SEMANTIC\_OS\_GETCWDU | 2 | `os.getcwdu()` |
| SEMANTIC\_COPY\_REG | 2 | `copy_reg` module |
| SEMANTIC\_MD5\_SHA\_MODULES | 2 | `md5.new()`, `sha.new()` |
| SEMANTIC\_HEX\_DECODE | 2 | `str.decode('hex')` |
| SEMANTIC\_RAW\_INPUT | 2 | `raw_input()` |
| SEMANTIC\_DIV | 1 | `__div__` method |
| SEMANTIC\_NONZERO | 1 | `__nonzero__` method |
| SEMANTIC\_SYS\_MAXINT | 1 | `sys.maxint` |
| SEMANTIC\_SYS\_EXITFUNC | 1 | `sys.exitfunc` |
| SEMANTIC\_SETS\_MODULE | 1 | `sets.Set` |
| SEMANTIC\_OS\_POPEN | 1 | `os.popen()` |
| SEMANTIC\_XREADLINES | 1 | `file.xreadlines()` |
| SEMANTIC\_TYPES\_INSTANCETYPE | 1 | `types.InstanceType` |
| SEMANTIC\_INTERN | 1 | `intern()` builtin |

### Import Issues (46 total)

| Category | Count | Description |
|---|---|---|
| IMPORT\_REMOVED\_STDLIB | 45 | Removed/renamed stdlib modules (ConfigParser, Queue, cPickle, etc.) |
| IMPORT\_DISTUTILS | 1 | `distutils.core` -- **BLOCKER** for Python 3.12 |

### Data Layer Issues (19 counted + 2 cross-cutting)

| Category | Count | Description |
|---|---|---|
| DATA\_ORD\_ON\_BYTES | 14 | `ord()` on bytes indexing (redundant in Py3) |
| DATA\_SOCKET\_RECV | 5 | `socket.recv()` returns bytes in Py3 |
| DATA\_ENCODING\_BOUNDARY | -- | str/bytes/unicode at I/O boundaries (cross-cutting) |
| DATA\_STRUCT\_MIXED | -- | struct.pack results mixed with str ops (cross-cutting) |

---

## Automatable vs. Manual Split

### Automatable (302 issues, 43.2%)

Pure syntax transforms that `2to3`, `pyupgrade`, or similar tools handle reliably with
no behavioral risk:

- Print statements and chevrons: 188
- Exception syntax (comma to as): 66
- Long literal suffixes: 40
- Octal literals: 4
- exec statement: 2
- Backtick repr, diamond operator: 2

### Mechanical (82 issues, 11.7%)

Straightforward renames and replacements. Low ambiguity, but worth a quick spot-check
after automated application:

- Dict method renames (iteritems, viewkeys, has\_key): 47
- Builtin renames (xrange, raw\_input, next(), intern): 22
- Dunder renames (\_\_nonzero\_\_, func\_name, im\_func, xreadlines): 13

### Manual Review Required (315 issues, 45.1%)

These require human judgment due to behavioral differences, data-type semantics,
or context-dependent correctness:

- Type system (unicode, long, basestring): 95
- Import rewrites (removed stdlib, implicit relative): 94
- Data layer (ord-on-bytes, socket recv, integer division): 26
- Module replacements (cPickle, copy\_reg, md5/sha, imp, commands): 22
- Behavioral changes (reduce, map/filter, operator, cmp, StandardError): 30
- Exception mechanics (raise syntax, sys.exc\_attrs, tuple unpacking): 15
- Miscellaneous (file(), metaclass, json encoding, exec, etc.): 33

---

## File Risk Distribution

| Risk Level | File Count | Issue Count | % of Total Issues |
|---|---|---|---|
| Critical (>= 15.0 density) | 7 | 59 | 8.4% |
| High (10.0 - 14.9 density) | 13 | 372 | 53.2% |
| Medium (5.0 - 9.9 density) | 14 | 251 | 35.9% |
| Low (< 5.0 density) | 5 | 40 | 5.7% |
| Clean (0 issues) | 6 | 0 | 0% |

The 13 high-density files contain over half of all issues and should be the primary
focus of migration effort. The 7 critical-density files are mostly small `__init__.py`
stubs (quick fixes) plus `report_generator.py` which needs substantive work.

---

## Baseline Reference

This report captures the starting state of the codebase before any Python 2 to 3 migration
work begins. All metrics are measured against the original Python 2.7 code at commit
`c4c0165`.

Migration progress will be tracked as:

- **Issue count reduction**: from 699 toward 0
- **Category elimination**: removing entire categories (e.g., all 185 print statements)
- **Density improvement**: per-file density trending downward
- **Severity clearance**: critical and high severity counts reaching 0

The first milestone is clearing the 302 automatable syntax issues, which can be done
in a single pass with `2to3` or `pyupgrade` and represents a 43% reduction.
