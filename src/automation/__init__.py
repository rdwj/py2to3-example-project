# -*- coding: utf-8 -*-
"""
Automation subsystem for the Legacy Industrial Data Platform.

This package provides task scheduling, script execution, and plugin
management for automated data collection, batch processing, and report
generation across the plant's sensor networks and control systems.
"""


from .scheduler import TaskScheduler, ScheduledTask, TaskWorker
from .script_runner import ScriptRunner, ScriptContext, ScriptResult
from .plugin_loader import PluginLoader, PluginMeta, PluginBase, PluginRegistry
