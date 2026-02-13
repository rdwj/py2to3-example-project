"""Flake8 plugin for Python 2-to-3 data-layer migration checks.

These rules focus on bytes/str boundary issues that are difficult to catch
with pure AST analysis and require pattern-matching on source text.

Rule codes:
    E950 - Binary protocol module missing explicit binary mode in file open
    E951 - Pickle usage without explicit protocol version
    E952 - String literal concatenated with bytes variable (likely Py3 TypeError)
    E953 - Socket recv() result used without decode/explicit bytes handling

Load as a flake8 plugin via entry_points or ``--select E95``.
"""

import ast
import re
import sys


class Py2DataLayerChecker:
    """Flake8 checker for bytes/str boundary issues in Py2-to-3 migration."""

    name = "flake8-py2-data-layer"
    version = "1.0.0"

    def __init__(self, tree, filename="(none)", lines=None):
        self.tree = tree
        self.filename = filename
        self.lines = lines or []

    def run(self):
        """Yield (line, col, message, type) tuples for each violation."""
        yield from self._check_open_modes()
        yield from self._check_pickle_protocol()
        yield from self._check_str_bytes_concat()
        yield from self._check_socket_recv()

    # -----------------------------------------------------------------
    # E950: Binary protocol module missing explicit binary mode
    # -----------------------------------------------------------------
    def _check_open_modes(self):
        """Flag open()/file() calls in protocol-heavy modules without
        explicit binary mode ('rb'/'wb') when the context suggests binary
        data is involved.
        """
        # Only flag in files that import struct or socket (binary protocol files)
        source = "\n".join(self.lines)
        has_struct = "import struct" in source
        has_socket = "import socket" in source
        if not has_struct and not has_socket:
            return

        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr

            if func_name not in ("open", "file"):
                continue

            # Check the mode argument
            mode = None
            if len(node.args) >= 2:
                mode_node = node.args[1]
                if isinstance(mode_node, ast.Constant) and isinstance(
                    mode_node.value, str
                ):
                    mode = mode_node.value
            else:
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value

            if mode is None:
                # No mode specified in a binary protocol module
                yield (
                    node.lineno,
                    node.col_offset,
                    "E950 {func}() in binary protocol module without explicit "
                    "mode argument; use 'rb' or 'wb' for binary data".format(
                        func=func_name
                    ),
                    type(self),
                )
            elif "b" not in mode:
                # Text mode in a binary protocol module -- may be intentional,
                # but worth flagging for review
                yield (
                    node.lineno,
                    node.col_offset,
                    "E950 {func}() in binary protocol module opened in text "
                    "mode '{mode}'; verify binary data is not being written "
                    "here".format(func=func_name, mode=mode),
                    type(self),
                )

    # -----------------------------------------------------------------
    # E951: Pickle usage without explicit protocol version
    # -----------------------------------------------------------------
    def _check_pickle_protocol(self):
        """Flag pickle.dump()/dumps() calls that do not specify a protocol."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in ("dump", "dumps"):
                continue

            # Check if the call target looks like pickle/cPickle
            caller = None
            if isinstance(func.value, ast.Name):
                caller = func.value.id
            if caller not in ("pickle", "cPickle"):
                continue

            # dump() expects: dump(obj, file, protocol=None)
            # dumps() expects: dumps(obj, protocol=None)
            has_protocol = False
            if func.attr == "dump" and len(node.args) >= 3:
                has_protocol = True
            elif func.attr == "dumps" and len(node.args) >= 2:
                has_protocol = True
            else:
                for kw in node.keywords:
                    if kw.arg == "protocol":
                        has_protocol = True
                        break

            if not has_protocol:
                yield (
                    node.lineno,
                    node.col_offset,
                    "E951 {caller}.{func}() called without explicit protocol "
                    "version; specify protocol=2 for Py2 compat or "
                    "protocol=pickle.HIGHEST_PROTOCOL for Py3-only".format(
                        caller=caller, func=func.attr
                    ),
                    type(self),
                )

    # -----------------------------------------------------------------
    # E952: String literal concatenated with bytes variable
    # -----------------------------------------------------------------
    _STR_BYTES_CONCAT_RE = re.compile(
        r'(?:'
        # Pattern 1: "string" + <bytes_func_call>  e.g.  "X" + struct.pack(...)
        r'"[^"]*"\s*\+\s*(?:struct\.pack|socket\.recv|\.recv)'
        r'|'
        # Pattern 2: <bytes_result> + "string"
        r'(?:struct\.pack|\.recv)\([^)]*\)\s*\+\s*"[^"]*"'
        r'|'
        # Pattern 3: empty string initialiser for binary accumulator
        r'(?:out|body|buf|data|result|payload|chunk)\s*=\s*""'
        r')'
    )

    def _check_str_bytes_concat(self):
        """Flag lines where a string literal is concatenated with something
        that returns bytes (struct.pack, recv, etc.).
        """
        # Only check in files with struct or socket usage
        source = "\n".join(self.lines)
        has_struct = "import struct" in source
        has_socket = "import socket" in source
        if not has_struct and not has_socket:
            return

        for lineno, line in enumerate(self.lines, start=1):
            # Skip comments
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            match = self._STR_BYTES_CONCAT_RE.search(line)
            if match:
                yield (
                    lineno,
                    match.start(),
                    "E952 Possible str/bytes concatenation; string literal "
                    "may need to be bytes literal (b\"...\") for Python 3 "
                    "compatibility",
                    type(self),
                )

    # -----------------------------------------------------------------
    # E953: Socket recv() without decode / explicit bytes handling
    # -----------------------------------------------------------------
    _RECV_ASSIGN_RE = re.compile(
        r"(\w+)\s*=\s*\w+\.recv\("
    )
    _DECODE_PATTERN = re.compile(
        r"\.decode\(|bytes\(|bytearray\(|struct\.unpack"
    )

    def _check_socket_recv(self):
        """Flag recv() results that are used without explicit bytes handling.

        Looks for patterns like ``data = sock.recv(N)`` and checks whether
        the next few lines contain a decode/bytes operation on the variable.
        """
        source = "\n".join(self.lines)
        if "import socket" not in source and ".recv(" not in source:
            return

        for lineno, line in enumerate(self.lines, start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            m = self._RECV_ASSIGN_RE.search(line)
            if not m:
                continue
            var_name = m.group(1)
            # Look ahead up to 5 lines for bytes handling
            lookahead = "\n".join(
                self.lines[lineno: min(lineno + 5, len(self.lines))]
            )
            # Check if the variable is used with decode/bytes/struct.unpack
            if self._DECODE_PATTERN.search(lookahead):
                continue
            # Also check if the variable is used with .join (bytes join pattern)
            if re.search(r'b?"?\.join\(', lookahead):
                continue
            yield (
                lineno,
                m.start(),
                "E953 recv() result '{var}' used without explicit "
                "decode() or bytes handling; in Python 3, recv() "
                "returns bytes, not str".format(var=var_name),
                type(self),
            )
