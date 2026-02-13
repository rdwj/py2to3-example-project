# -*- coding: utf-8 -*-
"""
Plugin system for the Legacy Industrial Data Platform.

Metaclass-based plugin registry and dynamic loader for processing plugins.
Plugins extend the data pipeline without modifying core code -- integrators
drop a module into the plugins directory and it is picked up on reload.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import importlib
import importlib.util
import time

from core.exceptions import PlatformError


class PluginRegistry:
    """Global registry of plugin classes, populated by PluginMeta."""
    _plugins = {}
    _load_order = []

    @classmethod
    def register(cls, name, plugin_class):
        if name in cls._plugins:
            print("WARNING: replacing plugin %r" % name)
        cls._plugins[name] = plugin_class
        if name not in cls._load_order:
            cls._load_order.append(name)

    @classmethod
    def get(cls, name):
        return cls._plugins.get(name)

    @classmethod
    def all_plugins(cls):
        return [(n, cls._plugins[n]) for n in cls._load_order if n in cls._plugins]

    @classmethod
    def clear(cls):
        cls._plugins.clear()
        cls._load_order = []

    @classmethod
    def count(cls):
        return len(cls._plugins)


class PluginMeta(type):
    """Metaclass that auto-registers ``PluginBase`` subclasses."""

    def __new__(mcs, name, bases, namespace):
        cls = type.__new__(mcs, name, bases, namespace)
        plugin_name = namespace.get("plugin_name")
        if plugin_name is not None:
            PluginRegistry.register(plugin_name, cls)
            print("Registered plugin: %s (%s)" % (plugin_name, name))
        return cls


class PluginBase(metaclass=PluginMeta):
    """Abstract base for plugins.  Subclasses set ``plugin_name``."""
    plugin_name = None
    plugin_version = "0.0"
    plugin_description = ""

    def __init__(self, config=None):
        self.config = config or {}
        self.active = False
        self._activated_at = None

    def activate(self):
        self.active = True
        self._activated_at = time.time()
        print("Plugin %r activated" % self.plugin_name)

    def deactivate(self):
        self.active = False

    def process(self, data_points):
        raise NotImplementedError("Subclass must implement process()")

    def get_info(self):
        return {"name": self.plugin_name, "version": self.plugin_version,
                "active": self.active}


class PluginLoader:
    """Lifecycle: discover -> load -> validate -> instantiate -> activate."""

    def __init__(self, plugin_directory=None, config=None):
        self.plugin_directory = plugin_directory or "/opt/platform/plugins"
        self.config = config or {}
        self._loaded_modules = {}
        self._instances = {}
        self._load_errors = {}

    def discover(self):
        if not os.path.isdir(self.plugin_directory):
            print("Plugin directory not found: %s" % self.plugin_directory)
            return []
        found = []
        for fn in sorted(os.listdir(self.plugin_directory)):
            if fn.startswith("_") or not fn.endswith(".py"):
                continue
            mod_name = fn[:-3]
            found.append((mod_name, os.path.join(self.plugin_directory, fn)))
            print("Discovered plugin: %s" % mod_name)
        return found

    def load_module(self, module_name, filepath):
        """Load or reload a plugin module."""
        try:
            if module_name in self._loaded_modules:
                print("Reloading: %s" % module_name)
                importlib.reload(self._loaded_modules[module_name])
            else:
                print("Loading: %s" % module_name)
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self._loaded_modules[module_name] = mod
            return self._loaded_modules[module_name]
        except Exception as e:
            self._load_errors[module_name] = str(e)
            print("Failed to load %s: %s" % (module_name, e))
            return None

    def load_all(self):
        found = self.discover()
        loaded = sum(1 for mn, fp in found if self.load_module(mn, fp) is not None)
        print("Loaded %d of %d plugins" % (loaded, len(found)))
        return loaded

    def validate_plugin_class(self, plugin_class):
        """Validate hooks are callable and inspect function/method attributes."""
        errors = []
        hook = getattr(plugin_class, "process", None)
        if hook is None:
            errors.append("Missing process()")
        elif not callable(hook):
            errors.append("process not callable")

        activate_hook = getattr(plugin_class, "activate", None)
        if activate_hook is not None and callable(activate_hook):
            self._inspect_method(activate_hook, "activate", errors)

        if hasattr(plugin_class, "process"):
            self._inspect_callback(plugin_class.process, "process", errors)

        if errors:
            print("Validation failed for %s: %s" % (plugin_class.__name__, "; ".join(errors)))
            return False
        return True

    def _inspect_callback(self, callback, name, errors):
        """Inspect __name__, __defaults__, __closure__."""
        actual = callback.__name__
        if actual != name:
            print("  %r backed by %r" % (name, actual))
        defaults = callback.__defaults__
        if defaults is not None:
            print("  %s: %d default(s)" % (name, len(defaults)))
        closure = callback.__closure__
        if closure is not None:
            print("  WARNING: %s closes over %d var(s)" % (name, len(closure)))

    def _inspect_method(self, method, name, errors):
        """Inspect __func__, __self__, and declaring class."""
        if not hasattr(method, "__func__"):
            return
        print("  %s wraps %s" % (name, method.__func__.__name__))
        if method.__self__ is not None:
            print("  %s bound to %r" % (name, method.__self__))
        # In Py3 bound methods don't have im_class; use type(__self__) instead
        if method.__self__ is not None:
            print("  %s from %s" % (name, type(method.__self__).__name__))

    def validate_all(self):
        return sum(1 for _, pc in PluginRegistry.all_plugins()
                   if self.validate_plugin_class(pc))

    def instantiate_plugin(self, plugin_name, plugin_config=None):
        pcls = PluginRegistry.get(plugin_name)
        if pcls is None:
            raise PlatformError("Unknown plugin: %s" % plugin_name)
        merged = dict(self.config)
        if plugin_config is not None:
            merged.update(plugin_config)
        try:
            inst = pcls(config=merged)
            self._instances[plugin_name] = inst
            print("Instantiated: %s v%s" % (plugin_name, inst.plugin_version))
            return inst
        except Exception as e:
            raise PlatformError("Failed to instantiate %s: %s" % (plugin_name, e))

    def instantiate_all(self, plugin_configs=None):
        cfgs = plugin_configs or {}
        count = 0
        for pn, pc in PluginRegistry.all_plugins():
            if not self.validate_plugin_class(pc):
                continue
            try:
                self.instantiate_plugin(pn, cfgs.get(pn))
                count += 1
            except PlatformError as e:
                print("Skipping %s: %s" % (pn, e))
        return count

    def activate_plugin(self, plugin_name):
        inst = self._instances.get(plugin_name)
        if inst is None:
            raise PlatformError("Plugin %s not instantiated" % plugin_name)
        inst.activate()
        return True

    def activate_all(self):
        activated = 0
        for pn, inst in self._instances.items():
            try:
                inst.activate()
                activated += 1
            except Exception as e:
                print("Failed to activate %s: %s" % (pn, e))
        print("Activated %d of %d plugins" % (activated, len(self._instances)))
        return activated

    def get_active_plugins(self):
        return [(n, i) for n, i in self._instances.items() if i.active]

    def process_data(self, data_points):
        results = {}
        for pn, inst in self.get_active_plugins():
            try:
                results[pn] = inst.process(data_points)
            except Exception as e:
                print("Plugin %s error: %s" % (pn, e))
                results[pn] = None
        return results

    def reload_plugin(self, plugin_name):
        """Hot-reload a plugin module."""
        mod = self._loaded_modules.get(plugin_name)
        if mod is None:
            raise PlatformError("Module %s not loaded" % plugin_name)
        existing = self._instances.get(plugin_name)
        if existing is not None:
            existing.deactivate()
        importlib.reload(mod)
        self.instantiate_plugin(plugin_name)
        self.activate_plugin(plugin_name)

    def get_status(self):
        return {"plugin_directory": self.plugin_directory,
                "loaded": len(self._loaded_modules),
                "registered": PluginRegistry.count(),
                "instantiated": len(self._instances),
                "active": len(self.get_active_plugins()),
                "errors": dict(self._load_errors)}
