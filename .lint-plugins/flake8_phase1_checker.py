"""Flake8 plugin for Phase 1 (Foundation) gate criteria."""
from __future__ import absolute_import, division, print_function, unicode_literals

import ast
import re


class Phase1Checker:
    """Check Phase 1 migration gate criteria."""

    name = 'py2to3-phase1'
    version = '1.0.0'

    def __init__(self, tree, filename='(none)', lines=None):
        self.tree = tree
        self.filename = filename
        self.lines = lines or []

    def run(self):
        """Yield lint errors."""
        # PY2001: Check for __future__ imports
        yield from self._check_future_imports()
        # PY2002: Check for distutils imports
        yield from self._check_distutils()
        # PY2003: Check shebangs reference python3
        yield from self._check_shebang()

    def _check_future_imports(self):
        """PY2001: All files must have from __future__ import."""
        required = {'print_function', 'division', 'absolute_import', 'unicode_literals'}
        found = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == '__future__':
                for alias in node.names:
                    found.add(alias.name)
        missing = required - found
        if missing:
            yield (1, 0, f'PY2001 Missing __future__ imports: {", ".join(sorted(missing))}', type(self))

    def _check_distutils(self):
        """PY2002: No distutils imports allowed."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module and 'distutils' in node.module:
                yield (node.lineno, node.col_offset,
                       f'PY2002 distutils import found: {node.module} (use setuptools)', type(self))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if 'distutils' in alias.name:
                        yield (node.lineno, node.col_offset,
                               f'PY2002 distutils import found: {alias.name} (use setuptools)', type(self))

    def _check_shebang(self):
        """PY2003: Shebangs must reference python3."""
        if self.lines and self.lines[0].startswith('#!'):
            shebang = self.lines[0]
            if 'python' in shebang and 'python3' not in shebang:
                yield (1, 0, 'PY2003 Shebang references python, not python3', type(self))
