# -*- coding: utf-8 -*-
"""
I/O protocol adapters for the Legacy Industrial Data Platform.

This package provides clients and listeners for the various industrial
communication protocols used on the plant floor: MODBUS TCP/RTU for PLC
register access, OPC-UA for automation node trees, RS-485 serial sensors,
and a lightweight MQTT implementation for IoT message buses.
"""


from .modbus_client import ModbusClient, ModbusFrame, RegisterBank
from .opcua_client import OpcUaClient, OpcUaNode, OpcUaSubscription
from .serial_sensor import SerialSensorReader, SensorPacket, SensorPacketStream
from .mqtt_listener import MqttListener, MqttMessage, MqttSubscription
