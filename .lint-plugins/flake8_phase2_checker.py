"""Flake8 plugin for Phase 2 (Mechanical Conversion) patterns."""
from __future__ import absolute_import, division, print_function, unicode_literals

import ast
import re


class Phase2Checker:
    """Check for Python 2 patterns that need Phase 2 conversion."""

    name = 'py2to3-phase2'
    version = '1.0.0'

    def __init__(self, tree, filename='(none)', lines=None):
        self.tree = tree
        self.filename = filename
        self.lines = lines or []

    def run(self):
        yield from self._check_print_statements()
        yield from self._check_except_comma()
        yield from self._check_has_key()
        yield from self._check_py2_builtins()
        yield from self._check_old_raise()
        yield from self._check_diamond_operator()
        yield from self._check_backtick_repr()
        yield from self._check_old_octal()

    def _check_print_statements(self):
        """PY2010: Flag print statements (not function calls)."""
        # In Python 3 AST, print statements become syntax errors
        # but with from __future__ import print_function, they parse as calls
        # So we check the source lines for print without parens
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped.startswith('print ') and not stripped.startswith('print('):
                if not stripped.startswith('print >>') and not stripped.startswith('#'):
                    yield (i, 0, 'PY2010 print statement (use print() function)', type(self))
            if stripped.startswith('print >>'):
                yield (i, 0, 'PY2011 print >> redirect syntax (use print(..., file=))', type(self))

    def _check_except_comma(self):
        """PY2012: Flag except Exception, e syntax."""
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            # Match: except SomeException, varname:
            if re.match(r'except\s+\w[\w.]*\s*,\s*\w+\s*:', stripped):
                yield (i, 0, 'PY2012 except comma syntax (use "except Exception as e:")', type(self))

    def _check_has_key(self):
        """PY2013: Flag dict.has_key() usage."""
        for i, line in enumerate(self.lines, 1):
            if '.has_key(' in line and not line.strip().startswith('#'):
                yield (i, 0, 'PY2013 dict.has_key() (use "key in dict")', type(self))

    def _check_py2_builtins(self):
        """PY2014-PY2017: Flag Py2 builtins."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                if node.id == 'xrange':
                    yield (node.lineno, node.col_offset, 'PY2014 xrange() (use range())', type(self))
                elif node.id == 'raw_input':
                    yield (node.lineno, node.col_offset, 'PY2015 raw_input() (use input())', type(self))
                elif node.id == 'execfile':
                    yield (node.lineno, node.col_offset, 'PY2016 execfile() (use exec(open(...).read()))', type(self))
                elif node.id == 'basestring':
                    yield (node.lineno, node.col_offset, 'PY2017 basestring (use str)', type(self))
                elif node.id == 'unicode':
                    yield (node.lineno, node.col_offset, 'PY2018 unicode type (use str)', type(self))
                elif node.id == 'long':
                    yield (node.lineno, node.col_offset, 'PY2019 long type (use int)', type(self))
            elif isinstance(node, ast.Attribute):
                if node.attr in ('iterkeys', 'itervalues', 'iteritems'):
                    yield (node.lineno, node.col_offset,
                           f'PY2020 dict.{node.attr}() (use .keys()/.values()/.items())', type(self))
                elif node.attr in ('viewkeys', 'viewvalues', 'viewitems'):
                    yield (node.lineno, node.col_offset,
                           f'PY2021 dict.{node.attr}() (use .keys()/.values()/.items())', type(self))
                elif node.attr == 'has_key':
                    yield (node.lineno, node.col_offset, 'PY2013 dict.has_key() (use "key in dict")', type(self))

    def _check_old_raise(self):
        """PY2022: Flag old-style raise syntax."""
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if re.match(r'raise\s+\w+\s*,\s*', stripped) and not stripped.startswith('#'):
                yield (i, 0, 'PY2022 old-style raise (use "raise Exception(msg)")', type(self))

    def _check_diamond_operator(self):
        """PY2023: Flag <> operator."""
        for i, line in enumerate(self.lines, 1):
            if '<>' in line and not line.strip().startswith('#') and not line.strip().startswith('"') and not line.strip().startswith("'"):
                yield (i, 0, 'PY2023 <> operator (use !=)', type(self))

    def _check_backtick_repr(self):
        """PY2024: Flag backtick repr."""
        for i, line in enumerate(self.lines, 1):
            # Backtick repr: `expr` — but not in strings or comments
            stripped = line.strip()
            if not stripped.startswith('#') and not stripped.startswith('"') and not stripped.startswith("'"):
                if re.search(r'`[^`]+`', stripped):
                    yield (i, 0, 'PY2024 backtick repr (use repr())', type(self))

    def _check_old_octal(self):
        """PY2025: Flag old-style octal literals."""
        for i, line in enumerate(self.lines, 1):
            if not line.strip().startswith('#'):
                # Match 0NNN where N is 0-7, but not 0x, 0b, 0o, or just 0
                if re.search(r'\b0[0-7]{2,}\b', line) and not re.search(r'\b0[xXbBoO]', line):
                    yield (i, 0, 'PY2025 old-style octal literal (use 0oNNN)', type(self))
