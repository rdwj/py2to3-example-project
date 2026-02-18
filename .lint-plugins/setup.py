"""Setup for py2to3 migration lint plugins."""
from setuptools import setup

setup(
    name='py2to3-lint-plugins',
    version='1.0.0',
    description='Custom flake8 plugins for Python 2 to 3 migration',
    py_modules=['flake8_phase1_checker', 'flake8_phase2_checker'],
    entry_points={
        'flake8.extension': [
            'PY20 = flake8_phase1_checker:Phase1Checker',
            'PY21 = flake8_phase2_checker:Phase2Checker',
        ],
    },
    install_requires=['flake8'],
)
