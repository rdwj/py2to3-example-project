#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legacy Industrial Data Platform -- setuptools setup script.

Install:
    python3 setup.py install

Create source distribution:
    python3 setup.py sdist
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from setuptools import setup, find_packages

setup(
    name="legacy-industrial-platform",
    version="2.4.1",
    description="Industrial sensor data collection, processing, and reporting platform",
    author="Acme Industrial Systems, Inc.",
    author_email="platform-dev@acme-industrial.example.com",
    url="http://intranet.acme-industrial.example.com/platform",
    license="Proprietary",
    python_requires=">=3.12",
    platforms=["linux"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Manufacturing",
        "License :: Other/Proprietary License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator",
    ],
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
