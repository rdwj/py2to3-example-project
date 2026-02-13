#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IoT sensor monitoring daemon for the Legacy Industrial Data Platform.

Runs background threads for RS-485 serial polling and MQTT telemetry
ingestion, buffering readings in a thread-safe queue for the storage
subsystem to consume.

Usage:
    python3 scripts/sensor_monitor.py [--serial PORT] [--mqtt HOST:PORT]

Runs until interrupted with Ctrl-C or SIGTERM.
"""


import os
import sys
import time
import _thread
import queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.io_protocols.serial_sensor import SerialSensorReader, SensorPacket
from src.io_protocols.mqtt_listener import MqttListener, MqttSubscription
from src.core.exceptions import PlatformError, ProtocolError
from src.core.config_loader import load_platform_config

# Shared queue for all incoming sensor data
_reading_queue = queue.Queue(maxsize=50000)
_running = True
_stats_lock = _thread.allocate_lock()
_serial_count = 0
_mqtt_count = 0


def serial_poll_loop(reader):
    """Background thread: poll RS-485 serial sensors continuously."""
    global _serial_count, _running
    print("MONITOR: serial poll thread started on %s" % reader.port_path)
    try:
        reader.open()
        for pkt in reader.stream_packets():
            if not _running:
                break
            dp = pkt.as_data_point()
            try:
                _reading_queue.put_nowait(dp)
            except queue.Full:
                print("MONITOR: reading queue full, dropping serial packet")
            _stats_lock.acquire()
            try:
                _serial_count += 1
            finally:
                _stats_lock.release()
    except Exception as e:
        print("MONITOR: serial thread error: %s" % str(e))
    finally:
        reader.close()
        print("MONITOR: serial poll thread exiting")


def mqtt_poll_loop(listener, subscription):
    """Background thread: drain MQTT subscription queue."""
    global _mqtt_count, _running
    print("MONITOR: MQTT poll thread started")
    while _running:
        msg = subscription.get_message(timeout=2.0)
        if msg is None:
            continue
        dp = msg.as_data_point()
        try:
            _reading_queue.put_nowait(dp)
        except queue.Full:
            print("MONITOR: reading queue full, dropping MQTT message")
        _stats_lock.acquire()
        try:
            _mqtt_count += 1
        finally:
            _stats_lock.release()
    print("MONITOR: MQTT poll thread exiting")


def parse_args(argv):
    """Parse command-line options from sys.argv."""
    opts = {"serial_port": None, "mqtt_host": None, "mqtt_port": 1883}
    i = 1
    while i < len(argv):
        if argv[i] == "--serial" and i + 1 < len(argv):
            opts["serial_port"] = argv[i + 1]
            i += 2
        elif argv[i] == "--mqtt" and i + 1 < len(argv):
            parts = argv[i + 1].split(":")
            opts["mqtt_host"] = parts[0]
            if len(parts) > 1:
                opts["mqtt_port"] = int(parts[1])
            i += 2
        else:
            i += 1
    return opts


def main():
    global _running

    print("MONITOR: Legacy Industrial Data Platform - Sensor Monitor")
    print("MONITOR: Starting at %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    config = load_platform_config()
    opts = parse_args(sys.argv)

    serial_port = opts["serial_port"] or config.get(
        "serial", "port", fallback="/dev/ttyS0")
    mqtt_host = opts["mqtt_host"] or config.get(
        "mqtt", "broker_host", fallback="localhost")
    mqtt_port = opts["mqtt_port"] or config.get_int(
        "mqtt", "broker_port", fallback=1883)

    # Start serial polling thread
    reader = SerialSensorReader(serial_port, baud_rate=9600, timeout=2.0)
    _thread.start_new_thread(serial_poll_loop, (reader,))

    # Start MQTT listener and polling thread
    listener = MqttListener(mqtt_host, port=mqtt_port)
    try:
        listener.connect()
        sub = listener.subscribe("plant/sensors/#")
        listener.start_listener()
        _thread.start_new_thread(mqtt_poll_loop, (listener, sub))
    except Exception as e:
        print("MONITOR: MQTT connection failed: %s (continuing without MQTT)" % str(e))

    # Main loop: drain the shared queue and print periodic stats
    print("MONITOR: Entering main loop (Ctrl-C to stop)")
    last_stats = time.time()
    try:
        while _running:
            try:
                dp = _reading_queue.get(block=True, timeout=1.0)
                print("  %s = %s  (q=%s)" % (dp.tag, dp.value, dp.quality))
            except queue.Empty:
                pass

            now = time.time()
            if now - last_stats >= 30.0:
                _stats_lock.acquire()
                try:
                    s_cnt = _serial_count
                    m_cnt = _mqtt_count
                finally:
                    _stats_lock.release()
                print("MONITOR: stats -- serial=%d  mqtt=%d  queue=%d" % (
                    s_cnt, m_cnt, _reading_queue.qsize(),
                ))
                last_stats = now
    except KeyboardInterrupt:
        print("")
        print("MONITOR: Interrupted, shutting down...")

    _running = False
    reader.close()
    listener.disconnect()
    print("MONITOR: Stopped at %s" % time.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
