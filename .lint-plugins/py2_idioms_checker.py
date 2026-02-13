"""Pylint plugin to detect Python 2 idioms during a phased Py2-to-3 migration.

Each checker is tagged with the earliest migration phase in which it is active.
Per-phase pylintrc files enable/disable message codes to enforce progressive
strictness as the migration advances.

Rule codes:
    PY2001 - PY2013  (see individual checker docstrings)

Load with:
    pylint --load-plugins=py2_idioms_checker ...
"""

import re

from astroid import nodes as astroid_nodes
from pylint.checkers import BaseChecker
from pylint.interfaces import HIGH


# ---------------------------------------------------------------------------
# Py2-only stdlib modules and their Py3 replacements
# ---------------------------------------------------------------------------
PY2_ONLY_IMPORTS = {
    "cPickle": "pickle",
    "cStringIO": "io (StringIO/BytesIO)",
    "StringIO": "io.StringIO",
    "ConfigParser": "configparser",
    "Queue": "queue",
    "thread": "threading or _thread",
    "commands": "subprocess",
    "__builtin__": "builtins",
    "copy_reg": "copyreg",
    "repr": "reprlib",
    "httplib": "http.client",
    "urllib2": "urllib.request",
    "xmlrpclib": "xmlrpc.client",
    "BaseHTTPServer": "http.server",
    "Cookie": "http.cookies",
    "cookielib": "http.cookiejar",
    "imp": "importlib",
    "md5": "hashlib",
    "sha": "hashlib",
    "sets": "builtin set",
}

# ---------------------------------------------------------------------------
# Regex patterns for AST-level text matching
# ---------------------------------------------------------------------------
_LONG_LITERAL_RE = re.compile(r"\b\d+[lL]\b")
_FUTURE_IMPORT_NAMES = frozenset(
    ["absolute_import", "division", "print_function", "unicode_literals"]
)


class Py2FutureImportChecker(BaseChecker):
    """PY2001: Verify all four ``__future__`` imports are present.

    Phase: 1 (earliest -- required for every file before any other work).
    """

    name = "py2-future-import"
    msgs = {
        "W9001": (
            "Missing __future__ import(s): %s. "
            "Add: from __future__ import absolute_import, division, "
            "print_function, unicode_literals",
            "py2-missing-future-import",
            "All modules must import the four standard __future__ names "
            "to enable forward-compatible behaviour before the full "
            "migration to Python 3.",
        ),
    }

    def visit_module(self, node):
        """Check the module-level AST for __future__ imports."""
        found = set()
        for child in node.body:
            if isinstance(child, astroid_nodes.ImportFrom):
                if child.modname == "__future__":
                    for name, _ in child.names:
                        found.add(name)
        missing = _FUTURE_IMPORT_NAMES - found
        if missing:
            self.add_message(
                "py2-missing-future-import",
                node=node,
                args=(", ".join(sorted(missing)),),
                confidence=HIGH,
            )


class Py2PrintStatementChecker(BaseChecker):
    """PY2002: Detect ``print`` used as a statement (not a function call).

    Phase: 2.

    Note: with ``from __future__ import print_function``, the parser treats
    ``print`` as a function, so this checker looks for bare ``print`` names
    that are *not* inside a Call node.  Under pure Py2 parsing (without the
    future import) the AST may represent print as a ``Print`` node instead;
    astroid normalises this in some configurations.
    """

    name = "py2-print-statement"
    msgs = {
        "W9002": (
            "print used as statement; convert to print() function call",
            "py2-print-statement",
            "Python 3 removed the print statement. Use print() instead.",
        ),
    }

    def visit_print(self, node):
        """Astroid may expose a Print node when parsing Py2 syntax."""
        self.add_message("py2-print-statement", node=node, confidence=HIGH)


class Py2ExceptSyntaxChecker(BaseChecker):
    """PY2003: Detect ``except Type, var:`` comma syntax.

    Phase: 2.
    """

    name = "py2-except-syntax"
    msgs = {
        "W9003": (
            "Old except syntax 'except %s, %s:'; use 'except %s as %s:' instead",
            "py2-except-comma-syntax",
            "Python 3 requires 'except ExcType as var:' syntax.",
        ),
    }

    def visit_excepthandler(self, node):
        """Check for the comma-form of except handlers.

        Astroid parses both forms into ExceptHandler nodes, but the comma
        form can be detected by checking the source text when available.
        We rely on the lineno/col_offset and attempt to read the source.
        """
        if node.name and node.type:
            # Try to read the actual source line to check for comma syntax
            try:
                # node.root() gives us the module, which may have file info
                module = node.root()
                if hasattr(module, "file") and module.file:
                    try:
                        with open(module.file, "r") as f:
                            lines = f.readlines()
                        if node.lineno and node.lineno <= len(lines):
                            line = lines[node.lineno - 1]
                            # Look for "except SomeType , varname :"
                            # but NOT "except SomeType as varname :"
                            except_match = re.search(
                                r"except\s+.+\s*,\s*\w+\s*:", line
                            )
                            as_match = re.search(
                                r"except\s+.+\s+as\s+\w+\s*:", line
                            )
                            if except_match and not as_match:
                                type_name = (
                                    node.type.as_string()
                                    if hasattr(node.type, "as_string")
                                    else str(node.type)
                                )
                                self.add_message(
                                    "py2-except-comma-syntax",
                                    node=node,
                                    args=(type_name, node.name, type_name, node.name),
                                    confidence=HIGH,
                                )
                    except (IOError, OSError):
                        pass
            except Exception:
                pass


class Py2XrangeChecker(BaseChecker):
    """PY2004: Detect ``xrange()`` calls.

    Phase: 2.
    """

    name = "py2-xrange"
    msgs = {
        "W9004": (
            "xrange() is removed in Python 3; use range() instead",
            "py2-xrange-usage",
            "Python 3 range() is lazy (equivalent to Py2 xrange).",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Name) and node.func.name == "xrange":
            self.add_message("py2-xrange-usage", node=node, confidence=HIGH)


class Py2DictIterMethodsChecker(BaseChecker):
    """PY2005: Detect ``.iteritems()``, ``.iterkeys()``, ``.itervalues()``.

    Phase: 2.
    """

    name = "py2-dict-iter-methods"
    _REMOVED_METHODS = frozenset(["iteritems", "iterkeys", "itervalues"])
    _REPLACEMENTS = {
        "iteritems": ".items()",
        "iterkeys": ".keys()",
        "itervalues": ".values()",
    }
    msgs = {
        "W9005": (
            ".%s() is removed in Python 3; use %s instead",
            "py2-dict-iter-method",
            "Python 3 .items()/.keys()/.values() return views (lazy).",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Attribute):
            if node.func.attrname in self._REMOVED_METHODS:
                replacement = self._REPLACEMENTS[node.func.attrname]
                self.add_message(
                    "py2-dict-iter-method",
                    node=node,
                    args=(node.func.attrname, replacement),
                    confidence=HIGH,
                )


class Py2StringTypeChecker(BaseChecker):
    """PY2006: Detect ``basestring`` and ``unicode`` type references.

    Phase: 3.
    """

    name = "py2-string-types"
    _PY2_TYPES = frozenset(["basestring", "unicode"])
    _REPLACEMENTS = {
        "basestring": "str (or (str, bytes) for isinstance checks)",
        "unicode": "str",
    }
    msgs = {
        "W9006": (
            "'%s' does not exist in Python 3; use %s instead",
            "py2-string-type",
            "Python 3 unified str as unicode. basestring and unicode "
            "are removed.",
        ),
    }

    def visit_name(self, node):
        if node.name in self._PY2_TYPES:
            replacement = self._REPLACEMENTS[node.name]
            self.add_message(
                "py2-string-type",
                node=node,
                args=(node.name, replacement),
                confidence=HIGH,
            )


class Py2HasKeyChecker(BaseChecker):
    """PY2007: Detect ``.has_key()`` method calls.

    Phase: 2.
    """

    name = "py2-has-key"
    msgs = {
        "W9007": (
            ".has_key(k) is removed in Python 3; use 'k in d' instead",
            "py2-has-key",
            "dict.has_key() was removed in Python 3. Use the 'in' operator.",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Attribute):
            if node.func.attrname == "has_key":
                self.add_message("py2-has-key", node=node, confidence=HIGH)


class Py2LongTypeChecker(BaseChecker):
    """PY2008: Detect ``long`` type and ``L`` suffix literals.

    Phase: 2.
    """

    name = "py2-long-type"
    msgs = {
        "W9008": (
            "'long' type does not exist in Python 3; use 'int' instead "
            "(int handles arbitrary precision)",
            "py2-long-type",
            "Python 3 unified int and long into int.",
        ),
        "W9018": (
            "Long literal with L suffix (e.g. 123L) is a SyntaxError in "
            "Python 3; remove the L suffix",
            "py2-long-literal",
            "Python 3 int handles arbitrary precision without a suffix.",
        ),
    }

    def visit_name(self, node):
        if node.name == "long":
            self.add_message("py2-long-type", node=node, confidence=HIGH)

    def visit_const(self, node):
        """Check for integer constants that had an L suffix in source."""
        if isinstance(node.value, int):
            # Try to detect L suffix from source text
            try:
                module = node.root()
                if hasattr(module, "file") and module.file:
                    with open(module.file, "r") as f:
                        lines = f.readlines()
                    if node.lineno and node.lineno <= len(lines):
                        line = lines[node.lineno - 1]
                        if _LONG_LITERAL_RE.search(line):
                            self.add_message(
                                "py2-long-literal", node=node, confidence=HIGH
                            )
            except (IOError, OSError, IndexError):
                pass


class Py2OnlyImportsChecker(BaseChecker):
    """PY2009: Detect imports of removed/renamed stdlib modules.

    Phase: 1.
    """

    name = "py2-only-imports"
    msgs = {
        "W9009": (
            "Module '%s' is removed/renamed in Python 3; use '%s' instead",
            "py2-only-import",
            "Several stdlib modules were renamed or removed in Python 3.",
        ),
    }

    def visit_import(self, node):
        for name, _ in node.names:
            top_level = name.split(".")[0]
            if top_level in PY2_ONLY_IMPORTS:
                self.add_message(
                    "py2-only-import",
                    node=node,
                    args=(top_level, PY2_ONLY_IMPORTS[top_level]),
                    confidence=HIGH,
                )

    def visit_importfrom(self, node):
        if node.modname:
            top_level = node.modname.split(".")[0]
            # Skip __future__ imports
            if top_level == "__future__":
                return
            if top_level in PY2_ONLY_IMPORTS:
                self.add_message(
                    "py2-only-import",
                    node=node,
                    args=(top_level, PY2_ONLY_IMPORTS[top_level]),
                    confidence=HIGH,
                )


class Py2BufferBuiltinChecker(BaseChecker):
    """PY2010: Detect ``buffer()`` builtin usage.

    Phase: 3.
    """

    name = "py2-buffer-builtin"
    msgs = {
        "W9010": (
            "buffer() is removed in Python 3; use memoryview() instead",
            "py2-buffer-builtin",
            "The buffer() builtin was replaced by memoryview() in Python 3.",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Name) and node.func.name == "buffer":
            self.add_message("py2-buffer-builtin", node=node, confidence=HIGH)


class Py2FileBuiltinChecker(BaseChecker):
    """PY2011: Detect ``file()`` builtin usage.

    Phase: 2.
    """

    name = "py2-file-builtin"
    msgs = {
        "W9011": (
            "file() builtin is removed in Python 3; use open() instead",
            "py2-file-builtin",
            "The file() constructor was removed in Python 3. Use open().",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Name) and node.func.name == "file":
            self.add_message("py2-file-builtin", node=node, confidence=HIGH)


class Py2ImplicitRelativeImportChecker(BaseChecker):
    """PY2012: Detect implicit relative imports.

    Phase: 1.

    Implicit relative imports (``from module import X`` without a leading dot
    when ``module`` is a sibling) are removed in Python 3.  This checker flags
    ``from X import ...`` statements where X matches a sibling module name
    inside the same package.
    """

    name = "py2-implicit-relative-import"
    msgs = {
        "W9012": (
            "Possible implicit relative import '%s'; "
            "use 'from .%s import ...' or an absolute import instead",
            "py2-implicit-relative-import",
            "Python 3 does not support implicit relative imports. "
            "Use explicit relative imports (from .module import ...) "
            "or fully-qualified absolute imports.",
        ),
    }

    def visit_importfrom(self, node):
        """Flag from-imports that lack a leading dot and match a sibling."""
        if node.level is not None and node.level > 0:
            # Already an explicit relative import
            return
        if not node.modname:
            return
        # Skip stdlib and __future__
        if node.modname.startswith("__future__"):
            return
        # Get the module's package directory
        module = node.root()
        if not hasattr(module, "file") or not module.file:
            return
        import os

        module_dir = os.path.dirname(module.file)
        # Check if there's a sibling module or package with this name
        top_name = node.modname.split(".")[0]
        sibling_py = os.path.join(module_dir, top_name + ".py")
        sibling_pkg = os.path.join(module_dir, top_name, "__init__.py")
        if os.path.exists(sibling_py) or os.path.exists(sibling_pkg):
            self.add_message(
                "py2-implicit-relative-import",
                node=node,
                args=(node.modname, node.modname),
                confidence=HIGH,
            )


class Py2OrdOnBytesChecker(BaseChecker):
    """PY2013: Detect ``ord()`` calls on single bytes from bytes objects.

    Phase: 3.

    In Python 3, indexing a bytes object returns an int directly, making
    ``ord()`` redundant (and potentially broken if the argument is already
    an int).
    """

    name = "py2-ord-on-bytes"
    msgs = {
        "W9013": (
            "ord() on byte data is unnecessary in Python 3 "
            "(bytes[i] already returns int); remove the ord() call",
            "py2-ord-on-bytes",
            "In Python 3, bytes indexing yields int directly. "
            "ord() on an int raises TypeError.",
        ),
    }

    def visit_call(self, node):
        if isinstance(node.func, astroid_nodes.Name) and node.func.name == "ord":
            # Flag all ord() calls -- in a migration context, any ord() call
            # on data coming from bytes objects is suspicious. A human reviewer
            # should verify each case.
            self.add_message("py2-ord-on-bytes", node=node, confidence=HIGH)


def register(linter):
    """Register all Py2 idiom checkers with the linter."""
    linter.register_checker(Py2FutureImportChecker(linter))
    linter.register_checker(Py2PrintStatementChecker(linter))
    linter.register_checker(Py2ExceptSyntaxChecker(linter))
    linter.register_checker(Py2XrangeChecker(linter))
    linter.register_checker(Py2DictIterMethodsChecker(linter))
    linter.register_checker(Py2StringTypeChecker(linter))
    linter.register_checker(Py2HasKeyChecker(linter))
    linter.register_checker(Py2LongTypeChecker(linter))
    linter.register_checker(Py2OnlyImportsChecker(linter))
    linter.register_checker(Py2BufferBuiltinChecker(linter))
    linter.register_checker(Py2FileBuiltinChecker(linter))
    linter.register_checker(Py2ImplicitRelativeImportChecker(linter))
    linter.register_checker(Py2OrdOnBytesChecker(linter))
