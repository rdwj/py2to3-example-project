# -*- coding: utf-8 -*-
"""
MQTT-like message listener for the Legacy Industrial Data Platform.
Simplified MQTT v3.1.1 over raw TCP for IoT sensor gateway telemetry.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import socket
import struct
import time
import json
import queue
import _thread

from src.core.types import DataPoint
from src.core.exceptions import MqttError

CONNECT    = 0x10
CONNACK    = 0x20
PUBLISH    = 0x30
SUBSCRIBE  = 0x80
SUBACK     = 0x90
PINGREQ    = 0xC0
PINGRESP   = 0xD0
DISCONNECT = 0xE0
CONNACK_OK = 0x00

_CONNACK_MSG = {0x00: "Accepted", 0x01: "Bad protocol", 0x02: "ID rejected",
                0x03: "Unavailable", 0x04: "Bad creds", 0x05: "Not authorized"}
DEFAULT_PORT = 1883


class MqttMessage(object):
    """Received message.  Payload is str from socket (Py2 bytes)."""

    def __init__(self, topic, payload, timestamp=None):
        self.topic = topic
        self.payload = payload
        self.timestamp = timestamp or time.time()
        self._json = None

    def json_payload(self):
        """Decode JSON payload."""
        if self._json is not None:
            return self._json
        try:
            self._json = json.loads(self.payload)
            return self._json
        except (ValueError, TypeError) as e:
            print("MQTT: JSON error on %s -- %s" % (self.topic, e))
            return None

    def as_data_point(self, vk="value", qk="quality"):
        d = self.json_payload()
        if d is None:
            return DataPoint(self.topic, None, self.timestamp, quality=0)
        return DataPoint(self.topic, d.get(vk), self.timestamp, d.get(qk, 192))

    def __repr__(self):
        return "MqttMessage(%r, %d bytes)" % (self.topic, len(self.payload))


class MqttSubscription(object):
    """Topic subscription with queue.Queue() buffer."""

    def __init__(self, topic_filter, qos=0, maxq=10000):
        self.topic_filter = topic_filter
        self.qos = qos
        self._q = queue.Queue(maxsize=maxq)
        self._n = 0

    def enqueue(self, msg):
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self._q.put_nowait(msg)
        self._n += 1

    def get_message(self, timeout=5.0):
        try:
            return self._q.get(block=True, timeout=timeout)
        except queue.Empty:
            return None

    def drain(self, limit=100):
        out = []
        for _ in range(limit):
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def matches(self, topic):
        fp, tp = self.topic_filter.split("/"), topic.split("/")
        for i in range(len(fp)):
            if fp[i] == "#":
                return True
            if i >= len(tp):
                return False
            if fp[i] != "+" and fp[i] != tp[i]:
                return False
        return len(fp) == len(tp)


class MqttListener(object):
    """Raw TCP MQTT client dispatching to subscriptions."""

    def __init__(self, host, port=DEFAULT_PORT, client_id=None, keepalive=60):
        self.host = host
        self.port = port
        self.client_id = client_id or "idp_%d" % int(time.time())
        self.keepalive = keepalive
        self._sock = None
        self._up = False
        self._subs = []
        self._on = False
        self._lock = _thread.allocate_lock()
        self._cnt = 0

    def connect(self):
        """Connect to MQTT broker."""
        print("MQTT: connecting to %s:%d" % (self.host, self.port))
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(10.0)
            self._sock.connect((self.host, self.port))
        except socket.error as e:
            raise MqttError("Connect failed: %s" % e)
        self._sock.send(self._mk_connect())
        ack = self._rx()
        if not ack or len(ack) < 4:
            raise MqttError("No CONNACK")
        rc = ord(ack[3])
        if rc != CONNACK_OK:
            raise MqttError("Refused: %s" % _CONNACK_MSG.get(rc, "%d" % rc))
        self._up = True
        print("MQTT: connected")

    def disconnect(self):
        self._on = False
        if self._sock and self._up:
            try:
                self._sock.send(struct.pack("BB", DISCONNECT, 0))
            except socket.error:
                pass
            try:
                self._sock.close()
            except socket.error:
                pass
            self._sock = None
            self._up = False
        print("MQTT: disconnected")

    def subscribe(self, topic_filter, qos=0):
        if not self._up:
            raise MqttError("Not connected")
        sub = MqttSubscription(topic_filter, qos)
        self._subs.append(sub)
        self._lock.acquire()
        try:
            self._sock.send(self._mk_sub(topic_filter, qos))
            self._rx()
        finally:
            self._lock.release()
        print("MQTT: subscribed to %s" % topic_filter)
        return sub

    def publish(self, topic, payload):
        if not self._up:
            raise MqttError("Not connected")
        self._lock.acquire()
        try:
            self._sock.send(self._mk_pub(topic, payload))
        finally:
            self._lock.release()
        print("MQTT: published %d bytes to %s" % (len(payload), topic))

    def start_listener(self):
        """Background via _thread.start_new_thread()."""
        self._on = True
        _thread.start_new_thread(self._loop, ())
        print("MQTT: listener started")

    def stop_listener(self):
        self._on = False

    def _mk_connect(self):
        vh = struct.pack(">H", 4) + "MQTT" + struct.pack("BBH", 4, 2, self.keepalive)
        pl = struct.pack(">H", len(self.client_id)) + self.client_id
        return struct.pack("B", CONNECT) + self._el(len(vh) + len(pl)) + vh + pl

    def _mk_sub(self, topic, qos):
        vh = struct.pack(">H", (self._cnt + 1) & 0xFFFF)
        pl = struct.pack(">H", len(topic)) + topic + struct.pack("B", qos)
        return struct.pack("B", SUBSCRIBE | 2) + self._el(len(vh) + len(pl)) + vh + pl

    def _mk_pub(self, topic, payload):
        vh = struct.pack(">H", len(topic)) + topic
        return struct.pack("B", PUBLISH) + self._el(len(vh) + len(payload)) + vh + payload

    def _el(self, n):
        """MQTT variable-length encoding."""
        out = ""
        while True:
            b = n % 128
            n = n // 128
            if n > 0:
                b |= 0x80
            out += struct.pack("B", b)
            if n <= 0:
                break
        return out

    def _rx(self):
        try:
            first = self._sock.recv(1)
            if not first:
                return None
            rem = self._dl()
            if rem == 0:
                return first + "\x00"
            body = ""
            while len(body) < rem:
                c = self._sock.recv(rem - len(body))
                if not c:
                    return None
                body += c
            return first + struct.pack("B", rem & 0x7F) + body
        except socket.timeout:
            return None
        except socket.error as e:
            print("MQTT: recv error -- %s" % e)
            return None

    def _dl(self):
        m, v = 1, 0
        for _ in range(4):
            b = self._sock.recv(1)
            if not b:
                return 0
            e = ord(b)
            v += (e & 0x7F) * m
            if not (e & 0x80):
                break
            m *= 128
        return v

    def _loop(self):
        while self._on and self._up:
            self._lock.acquire()
            try:
                pkt = self._rx()
            finally:
                self._lock.release()
            if pkt is None:
                if self._sock and self._up:
                    try:
                        self._sock.send(struct.pack("BB", PINGREQ, 0))
                    except socket.error:
                        pass
                continue
            pt = ord(pkt[0]) & 0xF0
            if pt == PUBLISH:
                try:
                    tl = struct.unpack(">H", pkt[2:4])[0]
                    topic, payload = pkt[4:4 + tl], pkt[4 + tl:]
                    self._cnt += 1
                    msg = MqttMessage(topic, payload)
                    for s in self._subs:
                        if s.matches(topic):
                            s.enqueue(msg)
                except (struct.error, IndexError) as e:
                    print("MQTT: bad PUBLISH -- %s" % e)
            elif pt == DISCONNECT:
                self._up = False
                break
