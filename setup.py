#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Legacy Industrial Data Platform -- distutils setup script.

Install:
    python setup.py install

Create source distribution:
    python setup.py sdist
"""

from distutils.core import setup

setup(
    name="legacy-industrial-platform",
    version="2.4.1",
    description="Industrial sensor data collection, processing, and reporting platform",
    author="Acme Industrial Systems, Inc.",
    author_email="platform-dev@acme-industrial.example.com",
    url="http://intranet.acme-industrial.example.com/platform",
    license="Proprietary",
    platforms=["linux"],
    packages=[
        "src",
        "src.core",
        "src.io_protocols",
        "src.data_processing",
        "src.storage",
        "src.reporting",
        "src.automation",
    ],
    scripts=[
        "scripts/run_platform.py",
        "scripts/batch_import.py",
        "scripts/sensor_monitor.py",
    ],
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
