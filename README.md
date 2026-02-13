# py2to3-example-project

A realistic Python 2.6/2.7 codebase designed as a test corpus for validating Python 2-to-3 migration skills and tooling. The project simulates a "Legacy Industrial Data Platform" that exercises 99+ distinct migration patterns across diverse data domains including IoT, SCADA, mainframe processing, and mixed-encoding data handling.

## Why This Exists

No existing open-source project combines comprehensive language-level migration patterns, realistic domain-specific scenarios, and an integrated codebase where modules interact. This project fills that gap by providing a coherent, realistic application rather than isolated test snippets.

## Project Narrative

The codebase represents an industrial data platform that:

- Ingests sensor data from IoT devices via serial/MQTT
- Communicates with SCADA systems via MODBUS and OPC-UA
- Processes mainframe batch files with EBCDIC encoding and COBOL-style packed decimals
- Parses CSV, XML, JSON, and unstructured text with mixed encodings
- Stores processed data in SQLite databases and file caches
- Generates reports, sends email alerts, and serves a basic web dashboard
- Runs automated tasks via a scheduler with a plugin system

## Migration Pattern Coverage

The codebase covers patterns across these categories:

| Category | Count | Examples |
|----------|-------|---------|
| Syntax Changes | 19 | `print` statement, `except` comma syntax, backtick repr, `<>` operator |
| Builtin/Type Changes | 16 | `xrange`, `raw_input`, `long`, `unicode`, `basestring`, `dict.has_key()` |
| Iterator/Generator Changes | 8 | `.next()` method, `__nonzero__`, `__cmp__`, `itertools.izip` |
| Standard Library Renames | 18 | `urllib2`, `ConfigParser`, `cPickle`, `StringIO`, `httplib` |
| String/Bytes/Encoding | 12 | str-is-bytes paradigm, EBCDIC codecs, CSV binary mode, socket types |
| Function/Method Attributes | 6 | `func_name`, `func_defaults`, `im_func`, `im_self` |
| sys/operator Module Changes | 8 | `sys.maxint`, `sys.exc_value`, `operator.isCallable()` |
| Domain-Specific Patterns | 12 | MODBUS register packing, COMP-3 packed decimal, serial byte boundaries |

See [PLAN.md](PLAN.md) for the complete pattern catalog with module mappings.

## Directory Layout

```
src/
  core/             Configuration, types, exceptions, utilities
  io_protocols/     MODBUS, OPC-UA, serial, MQTT adapters
  data_processing/  CSV, XML, JSON, mainframe parsers
  storage/          SQLite database, file store, cache
  reporting/        Report generation, email alerts, web dashboard
  automation/       Task scheduler, script runner, plugin loader
tests/              Unit and integration tests
scripts/            Command-line entry points
data/               Sample data files (EBCDIC, CSV, XML, JSON)
config/             Platform and logging configuration
```

## Design Constraints

- All code is syntactically valid Python 2.6/2.7
- External services are simulated with in-memory constructs and sample data
- Migration patterns arise naturally from domain logic, not contrived examples
- Modules import from each other to create realistic cross-module dependencies

## License

[MIT](LICENSE)
