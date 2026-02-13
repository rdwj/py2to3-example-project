Legacy Industrial Data Platform
===============================
Version 2.4.1


OVERVIEW

  The Legacy Industrial Data Platform collects, processes, and reports
  on sensor data from plant-floor control systems.  It integrates with
  MODBUS TCP/RTU PLCs, RS-485 serial sensors, OPC-UA automation nodes,
  and MQTT IoT gateways.  Nightly mainframe batch transfers (EBCDIC,
  COMP-3 packed decimal) from the corporate ERP are parsed and loaded
  into a local SQLite database for trend analysis and reporting.


REQUIREMENTS

  - Python 2.6 or 2.7 (CPython)
  - RHEL 5.x, 6.x, or CentOS equivalent
  - See requirements.txt for third-party packages
  - SQLite 3.6+
  - Access to plant network (10.1.40.0/24) for sensor protocols


INSTALLATION

  1. Unpack the source archive:
       tar xzf legacy-industrial-platform-2.4.1.tar.gz
       cd legacy-industrial-platform-2.4.1

  2. Install dependencies:
       pip install -r requirements.txt

  3. Install the platform:
       python setup.py install

  4. Copy configuration:
       cp config/platform.ini /etc/platform/platform.ini
     Edit the file to match your plant's network layout.


USAGE

  Interactive mode:
      python scripts/run_platform.py

  Batch mode (for cron):
      python scripts/run_platform.py --batch

  Mainframe import:
      python scripts/batch_import.py /opt/platform/incoming/mainframe

  Sensor monitoring daemon:
      python scripts/sensor_monitor.py --serial /dev/ttyS0 --mqtt 10.1.40.200:1883


DIRECTORY LAYOUT

  config/        Platform and logging configuration files
  data/          Sample data files for testing
  scripts/       Command-line entry points
  src/           Python source packages
    core/        Configuration, types, exceptions, utilities
    io_protocols/ MODBUS, OPC-UA, serial, MQTT adapters
    data_processing/  CSV, XML, JSON, mainframe parsers
    storage/     SQLite database, file store, cache
    reporting/   Report generation, email alerts, web dashboard
    automation/  Task scheduler, script runner, plugin loader
  tests/         Unit and integration tests


KNOWN ISSUES

  - The Python 2 csv module does not handle Unicode natively.  CSV files
    with non-ASCII content must be pre-processed through the encoding
    detection layer.  See src/data_processing/csv_processor.py.

  - MQTT keepalive may not work correctly through some industrial
    firewalls that strip TCP keepalive options.


CONTACT

  Platform Development Team
  platform-dev@acme-industrial.example.com
  Internal ext. 4071
