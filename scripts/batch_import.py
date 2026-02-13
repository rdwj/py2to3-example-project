#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mainframe batch import script for the Legacy Industrial Data Platform.

Processes EBCDIC-encoded flat files transferred nightly from the IBM z/OS
mainframe via Connect:Direct.  Parses fixed-width records using the
ERPX400 copybook layout and loads them into the platform database.

Called by cron at 02:30 UTC:
    30 2 * * * /opt/platform/scripts/batch_import.py /opt/platform/incoming/mainframe

Usage:
    python scripts/batch_import.py <input_dir_or_file> [--cache-dir DIR]
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from data_processing.mainframe_parser import (
    MainframeParser, CopybookLayout, EBCDIC_CODEC,
)
from core.exceptions import PlatformError, DataError, ParseError
from core.config_loader import load_platform_config


# ERPX400 transaction record layout -- 40 bytes per record
# Matches the COBOL copybook from the ERP team (rev. 2012-03-14)
RECORD_LENGTH = 40

def build_erpx400_layout():
    """Construct the CopybookLayout for ERPX400 transaction records."""
    layout = CopybookLayout("ERPX400-TRANS", RECORD_LENGTH)
    layout.add_field("ACCT-NAME",   0,  20, "char")
    layout.add_field("ACCT-NUMBER", 20, 10, "zoned")
    layout.add_field("TRANS-AMT",   30,  8, "comp3", decimal_places=2)
    layout.add_field("REC-TYPE",    38,  2, "char")
    return layout


def process_file(file_path, cache_dir):
    """Parse a single mainframe batch file and report results."""
    print "=" * 60
    print "Processing: %s" % file_path
    print "Started:    %s" % time.strftime("%Y-%m-%d %H:%M:%S")
    print "=" * 60

    layout = build_erpx400_layout()
    parser = MainframeParser(layout, cache_dir=cache_dir)

    f = file(file_path, "rb")
    try:
        file_size = os.path.getsize(file_path)
        expected_records = file_size / RECORD_LENGTH
        print "File size:  %d bytes (%d expected records)" % (
            file_size, expected_records,
        )
    finally:
        f.close()

    records = parser.parse_file(file_path)
    print ""
    print "Parse complete: %d records, %d errors" % (
        parser.records_parsed(), parser.errors_encountered(),
    )

    # Print first few records as a sanity check
    for rec in records[:5]:
        print "  #%04d  %-20s  ACCT=%s  AMT=%s  TYPE=%s" % (
            rec.record_number,
            rec.get("ACCT-NAME", "???"),
            rec.get("ACCT-NUMBER", "???"),
            rec.get("TRANS-AMT", "???"),
            rec.get("REC-TYPE", "??"),
        )
    if len(records) > 5:
        print "  ... (%d more records)" % (len(records) - 5)

    return len(records), parser.errors_encountered()


def main():
    if len(sys.argv) < 2:
        print "Usage: %s <input_dir_or_file> [--cache-dir DIR]" % sys.argv[0]
        sys.exit(1)

    input_path = sys.argv[1]
    cache_dir = None
    if "--cache-dir" in sys.argv:
        idx = sys.argv.index("--cache-dir")
        if idx + 1 < len(sys.argv):
            cache_dir = sys.argv[idx + 1]

    total_records = 0
    total_errors = 0

    try:
        if os.path.isdir(input_path):
            dat_files = sorted(
                f for f in os.listdir(input_path) if f.endswith(".dat")
            )
            if not dat_files:
                print "No .dat files found in %s" % input_path
                sys.exit(0)
            print "Found %d batch file(s) in %s" % (len(dat_files), input_path)
            for fname in dat_files:
                full_path = os.path.join(input_path, fname)
                n, errs = process_file(full_path, cache_dir)
                total_records += n
                total_errors += errs
        elif os.path.isfile(input_path):
            total_records, total_errors = process_file(input_path, cache_dir)
        else:
            print "ERROR: Path not found: %s" % input_path
            sys.exit(1)
    except (PlatformError, DataError, ParseError), e:
        print "BATCH ERROR: %s" % str(e)
        sys.exit(2)
    except Exception, e:
        print "UNEXPECTED ERROR: %s" % str(e)
        sys.exit(2)

    print ""
    print "Batch import finished at %s" % time.strftime("%Y-%m-%d %H:%M:%S")
    print "Total records: %d   Total errors: %d" % (total_records, total_errors)
    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
