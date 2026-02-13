#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for the Legacy Industrial Data Platform.

Starts platform services, loads configuration, and provides an
interactive command loop for operators.  Designed to run on
Python 2.6+ under RHEL 5/6 on the plant floor servers.

Usage:
    python3 scripts/run_platform.py [--config PATH] [--batch] [--verbose]
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

# Ensure src/ is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from core.config_loader import load_platform_config
from core.exceptions import PlatformError, ProtocolError, DataError
from core.types import DataPoint
from io_protocols.serial_sensor import SerialSensorReader
from io_protocols.mqtt_listener import MqttListener
from data_processing.mainframe_parser import MainframeParser, CopybookLayout
from data_processing.csv_processor import CsvProcessor
from storage.database import DatabaseManager
from storage.cache import CacheManager
from reporting.report_generator import ReportGenerator
from automation.scheduler import TaskScheduler, ScheduledTask


BANNER = (
    "================================================\n"
    "  Legacy Industrial Data Platform v2.4.1\n"
    "  (c) 2009-2014 Acme Industrial Systems, Inc.\n"
    "================================================"
)

COMMANDS = {
    "status":  "Show platform component status",
    "import":  "Run mainframe batch import",
    "sensors": "List registered sensors",
    "report":  "Generate daily summary report",
    "flush":   "Flush cache to database",
    "quit":    "Shut down the platform",
}


def parse_args(argv):
    """Minimal argument parsing via sys.argv (no argparse on 2.6)."""
    opts = {"config": None, "batch": False, "verbose": False}
    i = 1
    while i < len(argv):
        if argv[i] == "--config" and i + 1 < len(argv):
            opts["config"] = argv[i + 1]
            i += 2
        elif argv[i] == "--batch":
            opts["batch"] = True
            i += 1
        elif argv[i] == "--verbose":
            opts["verbose"] = True
            i += 1
        else:
            print "Unknown option: %s" % argv[i]
            i += 1
    return opts


def init_platform(config_path=None):
    """Load configuration and initialise core subsystems."""
    print "Initialising platform..."
    config = load_platform_config(config_path)
    config.dump()

    db_path = config.get("storage", "database_path", fallback="platform.db")
    db = DatabaseManager(db_path)
    cache = CacheManager(
        max_entries=config.get_int("cache", "max_entries", fallback=50000),
    )
    scheduler = TaskScheduler()

    print "Platform subsystems ready"
    return config, db, cache, scheduler


def run_interactive(config, db, cache, scheduler):
    """Interactive command loop using raw_input()."""
    print ""
    print "Type 'help' for available commands."
    while True:
        try:
            cmd = raw_input("platform> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print ""
            print "Shutting down..."
            break

        if cmd == "help":
            for name, desc in sorted(COMMANDS.items()):
                print "  %-10s %s" % (name, desc)
        elif cmd == "status":
            print "Database:  %s" % db
            print "Cache:     %s entries" % cache
            print "Scheduler: %s" % scheduler
        elif cmd == "report":
            try:
                gen = ReportGenerator()
                print "Report generation started at %s" % time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception, e:
                print "Report error: %s" % str(e)
        elif cmd == "quit":
            print "Shutting down platform..."
            break
        elif cmd == "":
            continue
        else:
            print "Unknown command: %s  (type 'help')" % cmd


def run_batch(config, db, cache, scheduler):
    """Non-interactive batch mode for cron or systemd."""
    print "Running in batch mode..."
    try:
        incoming = config.get("mainframe", "incoming_dir",
                              fallback="/opt/platform/incoming/mainframe")
        if os.path.isdir(incoming):
            for fname in os.listdir(incoming):
                if fname.endswith(".dat"):
                    print "Processing %s" % fname
        else:
            print "Incoming directory not found: %s" % incoming
    except Exception, e:
        print "Batch processing error: %s" % str(e)
        return 1
    print "Batch processing complete"
    return 0


def main():
    print BANNER
    opts = parse_args(sys.argv)

    try:
        config, db, cache, scheduler = init_platform(opts["config"])
    except PlatformError, e:
        print "FATAL: Platform init failed: %s" % str(e)
        sys.exit(1)
    except Exception, e:
        print "FATAL: Unexpected error during init: %s" % str(e)
        sys.exit(1)

    if opts["batch"]:
        rc = run_batch(config, db, cache, scheduler)
        sys.exit(rc)
    else:
        run_interactive(config, db, cache, scheduler)

    print "Platform stopped."


if __name__ == "__main__":
    main()
