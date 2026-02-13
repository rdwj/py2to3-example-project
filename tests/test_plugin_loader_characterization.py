# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/plugin_loader.py

Captures pre-migration behavior of:
- PluginRegistry class-level registry (register/get/all/clear)
- PluginMeta metaclass auto-registration via __metaclass__
- PluginBase lifecycle (activate/deactivate/process/get_info)
- PluginLoader discovery, loading, validation, instantiation
- Py2-specific: __metaclass__ syntax, func_name/func_defaults/func_closure,
  im_func/im_self/im_class, operator.isCallable, dict.iteritems, reload()
"""


import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.automation.plugin_loader import (
    PluginRegistry, PluginBase, PluginMeta, PluginLoader,
)
from src.core.exceptions import PlatformError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry is clean before and after each test."""
    PluginRegistry.clear()
    yield
    PluginRegistry.clear()


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a temporary plugin directory with sample plugin files."""
    d = tmp_path / "plugins"
    d.mkdir()
    # Write a simple plugin module
    plugin_code = '''
from src.automation.plugin_loader import PluginBase

class TestPlugin(PluginBase):
    plugin_name = "test_plugin"
    plugin_version = "1.0"
    plugin_description = "A test plugin"

    def process(self, data_points):
        return [dp for dp in data_points]
'''
    (d / "test_plugin.py").write_text(plugin_code)
    return str(d)


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    """Characterize the global plugin registry."""

    def test_register_and_get(self):
        """Captures: register a class by name and retrieve it."""
        class FakePlugin:
            pass
        PluginRegistry.register("fake", FakePlugin)
        assert PluginRegistry.get("fake") is FakePlugin

    def test_get_missing_returns_none(self):
        """Captures: unregistered name returns None."""
        assert PluginRegistry.get("nonexistent") is None

    def test_all_plugins_preserves_order(self):
        """Captures: all_plugins returns (name, cls) in registration order."""
        class A: pass
        class B: pass
        class C: pass
        PluginRegistry.register("alpha", A)
        PluginRegistry.register("beta", B)
        PluginRegistry.register("gamma", C)
        names = [n for n, _ in PluginRegistry.all_plugins()]
        assert names == ["alpha", "beta", "gamma"]

    def test_count(self):
        """Captures: count returns number of registered plugins."""
        assert PluginRegistry.count() == 0
        PluginRegistry.register("p1", object)
        assert PluginRegistry.count() == 1

    def test_clear(self):
        """Captures: clear empties both plugins dict and load order."""
        PluginRegistry.register("p1", object)
        PluginRegistry.clear()
        assert PluginRegistry.count() == 0
        assert PluginRegistry.all_plugins() == []

    def test_register_replaces_existing(self):
        """Captures: re-registering same name replaces the class."""
        class Old: pass
        class New: pass
        PluginRegistry.register("dup", Old)
        PluginRegistry.register("dup", New)
        assert PluginRegistry.get("dup") is New
        assert PluginRegistry.count() == 1


# ---------------------------------------------------------------------------
# PluginMeta / PluginBase
# ---------------------------------------------------------------------------

class TestPluginMetaAndBase:
    """Characterize metaclass auto-registration and PluginBase lifecycle."""

    @pytest.mark.py2_behavior
    def test_metaclass_auto_registers_subclass(self):
        """Captures: __metaclass__ = PluginMeta auto-registers subclasses.
        In Py3, metaclass uses class Foo(PluginBase, metaclass=PluginMeta)."""
        # Dynamically create a subclass to trigger metaclass
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "dynamic_plugin",
            "plugin_version": "2.0",
            "process": lambda self, data: data,
        }
        DynPlugin = PluginMeta("DynPlugin", (PluginBase,), attrs)
        assert PluginRegistry.get("dynamic_plugin") is DynPlugin

    def test_plugin_base_not_registered(self):
        """Captures: PluginBase itself has plugin_name=None, not registered."""
        # PluginBase.plugin_name is None, so it should not be in registry
        assert PluginRegistry.get(None) is None

    def test_plugin_activate_deactivate(self):
        """Captures: activate sets active=True, deactivate sets active=False."""
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "lifecycle_test",
            "process": lambda self, data: data,
        }
        Cls = PluginMeta("LifecyclePlugin", (PluginBase,), attrs)
        inst = Cls(config={"key": "value"})
        assert inst.active is False
        inst.activate()
        assert inst.active is True
        assert inst._activated_at is not None
        inst.deactivate()
        assert inst.active is False

    def test_plugin_get_info(self):
        """Captures: get_info returns dict with name, version, active."""
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "info_test",
            "plugin_version": "3.0",
            "process": lambda self, data: data,
        }
        Cls = PluginMeta("InfoPlugin", (PluginBase,), attrs)
        inst = Cls()
        info = inst.get_info()
        assert info["name"] == "info_test"
        assert info["version"] == "3.0"
        assert info["active"] is False

    def test_plugin_process_raises_not_implemented(self):
        """Captures: base process() raises NotImplementedError."""
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "abstract_test",
        }
        Cls = PluginMeta("AbstractPlugin", (PluginBase,), attrs)
        inst = Cls()
        with pytest.raises(NotImplementedError):
            inst.process([])


# ---------------------------------------------------------------------------
# PluginLoader
# ---------------------------------------------------------------------------

class TestPluginLoader:
    """Characterize the plugin loader lifecycle."""

    def test_discover_empty_directory(self, tmp_path):
        """Captures: discover returns empty list for dir with no .py files."""
        d = tmp_path / "empty_plugins"
        d.mkdir()
        loader = PluginLoader(plugin_directory=str(d))
        found = loader.discover()
        assert found == []

    def test_discover_skips_underscore_files(self, tmp_path):
        """Captures: files starting with _ are excluded from discovery."""
        d = tmp_path / "plugins"
        d.mkdir()
        (d / "__init__.py").write_text("# init")
        (d / "_private.py").write_text("# private")
        (d / "valid.py").write_text("# valid")
        loader = PluginLoader(plugin_directory=str(d))
        found = loader.discover()
        assert len(found) == 1
        assert found[0][0] == "valid"

    def test_discover_nonexistent_directory(self):
        """Captures: nonexistent directory returns empty list."""
        loader = PluginLoader(plugin_directory="/no/such/path")
        found = loader.discover()
        assert found == []

    def test_instantiate_unknown_plugin_raises(self):
        """Captures: instantiating unregistered plugin raises PlatformError."""
        loader = PluginLoader()
        with pytest.raises(PlatformError, match="Unknown plugin"):
            loader.instantiate_plugin("nonexistent")

    def test_get_status_initial(self):
        """Captures: status dict structure after init."""
        loader = PluginLoader()
        status = loader.get_status()
        assert "loaded" in status
        assert "registered" in status
        assert "instantiated" in status
        assert "active" in status
        assert "errors" in status
        assert status["loaded"] == 0

    def test_instantiate_and_activate(self):
        """Captures: full lifecycle through manual registration."""
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "manual_test",
            "plugin_version": "1.0",
            "process": lambda self, data: [d for d in data],
        }
        PluginMeta("ManualPlugin", (PluginBase,), attrs)
        loader = PluginLoader(config={"global": True})
        inst = loader.instantiate_plugin("manual_test", {"local": True})
        assert inst is not None
        assert inst.config["global"] is True
        assert inst.config["local"] is True
        loader.activate_plugin("manual_test")
        active = loader.get_active_plugins()
        assert len(active) == 1

    def test_process_data_dispatches_to_active(self):
        """Captures: process_data calls process() on each active plugin."""
        attrs = {
            "__metaclass__": PluginMeta,
            "plugin_name": "proc_test",
            "process": lambda self, data: len(data),
        }
        PluginMeta("ProcPlugin", (PluginBase,), attrs)
        loader = PluginLoader()
        loader.instantiate_plugin("proc_test")
        loader.activate_plugin("proc_test")
        results = loader.process_data([1, 2, 3])
        assert results["proc_test"] == 3
