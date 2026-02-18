#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legacy Industrial Data Platform -- setuptools setup script.

Install:
    python3 setup.py install
    OR
    pip install .

Create source distribution:
    python3 setup.py sdist
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from setuptools import setup, find_packages

# Read requirements from requirements.txt
def read_requirements():
    with open('requirements.txt') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="legacy-industrial-platform",
    version="2.4.1",
    description="Industrial sensor data collection, processing, and reporting platform",
    author="Acme Industrial Systems, Inc.",
    author_email="platform-dev@acme-industrial.example.com",
    url="http://intranet.acme-industrial.example.com/platform",
    license="Proprietary",
    platforms=["linux"],
    python_requires='>=3.12',
    packages=[
        "src",
        "src.core",
        "src.io_protocols",
        "src.data_processing",
        "src.storage",
        "src.reporting",
        "src.automation",
    ],
    install_requires=read_requirements(),
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
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Manufacturing',
        'License :: Other/Proprietary License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: System :: Hardware',
        'Topic :: System :: Monitoring',
    ],
)
