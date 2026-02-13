"""Minimal setup.py shim -- only needed for data_files.

All other metadata lives in pyproject.toml.  data_files is a legacy
distutils feature that setuptools still supports only through setup.py
or setup.cfg, not through pyproject.toml's [tool.setuptools] table.
"""

from setuptools import setup

setup(
    data_files=[
        ("config", ["config/platform.ini", "config/logging.conf"]),
        ("data", [
            "data/sample_ebcdic.dat",
            "data/sensor_readings.csv",
            "data/scada_config.xml",
            "data/sample_records.json",
        ]),
    ],
)
