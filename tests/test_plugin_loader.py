# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/plugin_loader.py

Captures current behavior of the plugin system including:
- __metaclass__ auto-registration (A12)
- reload() builtin (B10)
- operator.isCallable() (H1)
- Function attributes: func_name, func_defaults, func_closure (F1-F3)
- Method attributes: im_func, im_self, im_class (F4-F6)
- dict.iteritems(), dict.has_key() (D1, E2)
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import tempfile
from unittest import mock

import pytest

from src.automation.plugin_loader import (
    PluginBase,
    PluginLoader,
    PluginMeta,
    PluginRegistry,
)
from src.core.exceptions import PlatformError


@pytest.fixture
def plugin_dir():
    """Create a temporary plugin directory."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Cleanup
    import shutil
    try:
        shutil.rmtree(tmpdir)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the plugin registry before each test."""
    PluginRegistry.clear()
    yield
    PluginRegistry.clear()


class TestPluginRegistry:
    """Test the global plugin registry."""

    def test_register_plugin(self):
        """Test plugin registration."""
        class TestPlugin(object):
            pass

        PluginRegistry.register("test_plugin", TestPlugin)

        assert PluginRegistry.get("test_plugin") == TestPlugin
        assert PluginRegistry.count() == 1

    def test_register_duplicate_warns(self, capsys):
        """Test registering duplicate plugin name prints warning."""
        class Plugin1(object):
            pass

        class Plugin2(object):
            pass

        PluginRegistry.register("dup", Plugin1)
        PluginRegistry.register("dup", Plugin2)

        captured = capsys.readouterr()
        assert "replacing plugin" in captured.out.lower()
        assert PluginRegistry.get("dup") == Plugin2

    def test_all_plugins_preserves_order(self):
        """Test all_plugins() returns plugins in registration order."""
        class PluginA(object):
            pass

        class PluginB(object):
            pass

        class PluginC(object):
            pass

        PluginRegistry.register("plugin_a", PluginA)
        PluginRegistry.register("plugin_b", PluginB)
        PluginRegistry.register("plugin_c", PluginC)

        plugins = PluginRegistry.all_plugins()
        names = [name for name, cls in plugins]
        assert names == ["plugin_a", "plugin_b", "plugin_c"]

    def test_clear_registry(self):
        """Test clearing the registry."""
        class TestPlugin(object):
            pass

        PluginRegistry.register("test", TestPlugin)
        assert PluginRegistry.count() == 1

        PluginRegistry.clear()
        assert PluginRegistry.count() == 0
        assert PluginRegistry.get("test") is None


class TestPluginMeta:
    """Test the metaclass auto-registration."""

    def test_metaclass_auto_registration(self):
        """Test that __metaclass__ triggers auto-registration."""
        class AutoPlugin(object, metaclass=PluginMeta):
            plugin_name = "auto_registered"

        # Should be automatically registered
        assert PluginRegistry.get("auto_registered") == AutoPlugin

    def test_base_class_without_name_not_registered(self):
        """Test that base classes without plugin_name don't register."""
        initial_count = PluginRegistry.count()

        class AbstractPlugin(object, metaclass=PluginMeta):
            plugin_name = None

        # Should not increase count
        assert PluginRegistry.count() == initial_count


class TestPluginBase:
    """Test the PluginBase abstract class."""

    def test_plugin_base_instantiation(self):
        """Test creating plugin instances with config."""
        class TestPlugin(PluginBase):
            plugin_name = "test_inst"
            plugin_version = "1.0"

        config = {"threshold": 100, "enabled": True}
        plugin = TestPlugin(config)

        assert plugin.config == config
        assert plugin.active is False
        assert plugin.plugin_name == "test_inst"
        assert plugin.plugin_version == "1.0"

    def test_activate_deactivate(self):
        """Test plugin activation/deactivation."""
        class SimplePlugin(PluginBase):
            plugin_name = "simple"

        plugin = SimplePlugin()
        assert plugin.active is False

        plugin.activate()
        assert plugin.active is True
        assert plugin._activated_at is not None

        plugin.deactivate()
        assert plugin.active is False

    def test_get_info(self):
        """Test get_info() returns expected structure."""
        class InfoPlugin(PluginBase):
            plugin_name = "info_test"
            plugin_version = "2.5"

        plugin = InfoPlugin()
        info = plugin.get_info()

        assert info["name"] == "info_test"
        assert info["version"] == "2.5"
        assert info["active"] is False

        plugin.activate()
        info = plugin.get_info()
        assert info["active"] is True

    def test_process_not_implemented(self):
        """Test that process() raises NotImplementedError in base class."""
        class NoProcessPlugin(PluginBase):
            plugin_name = "no_process"

        plugin = NoProcessPlugin()
        with pytest.raises(NotImplementedError):
            plugin.process([])


class TestPluginLoader:
    """Test the plugin loader lifecycle."""

    def test_discover_empty_directory(self, plugin_dir):
        """Test discovery in empty directory."""
        loader = PluginLoader(plugin_directory=plugin_dir)
        found = loader.discover()
        assert found == []

    def test_discover_plugin_files(self, plugin_dir):
        """Test discovering .py files in plugin directory."""
        # Create test plugin files
        with open(os.path.join(plugin_dir, "plugin_a.py"), "w") as f:
            f.write("# Plugin A\n")

        with open(os.path.join(plugin_dir, "plugin_b.py"), "w") as f:
            f.write("# Plugin B\n")

        # Should ignore non-.py and _*.py files
        with open(os.path.join(plugin_dir, "readme.txt"), "w") as f:
            f.write("readme\n")

        with open(os.path.join(plugin_dir, "_internal.py"), "w") as f:
            f.write("# internal\n")

        loader = PluginLoader(plugin_directory=plugin_dir)
        found = loader.discover()

        assert len(found) == 2
        names = [name for name, path in found]
        assert "plugin_a" in names
        assert "plugin_b" in names

    def test_load_module(self, plugin_dir):
        """Test loading a plugin module with imp.load_source()."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class SamplePlugin(PluginBase):
    plugin_name = "sample"
    plugin_version = "1.0"

    def process(self, data_points):
        return len(data_points)
"""
        plugin_path = os.path.join(plugin_dir, "sample.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        mod = loader.load_module("sample", plugin_path)

        assert mod is not None
        assert "SamplePlugin" in dir(mod)

    def test_reload_module(self, plugin_dir):
        """Test reloading a module with reload() builtin."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class ReloadPlugin(PluginBase):
    plugin_name = "reload_test"
    VERSION = 1

    def process(self, data_points):
        return self.VERSION
"""
        plugin_path = os.path.join(plugin_dir, "reload_test.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)

        # Load first version
        mod1 = loader.load_module("reload_test", plugin_path)
        assert mod1.ReloadPlugin.VERSION == 1

        # Modify the file
        plugin_code_v2 = plugin_code.replace("VERSION = 1", "VERSION = 2")
        with open(plugin_path, "w") as f:
            f.write(plugin_code_v2)

        # Reload
        mod2 = loader.load_module("reload_test", plugin_path)
        assert mod2.ReloadPlugin.VERSION == 2

    def test_load_all(self, plugin_dir):
        """Test loading all discovered plugins."""
        # Create multiple plugin files
        for i in range(3):
            code = """
from src.automation.plugin_loader import PluginBase

class Plugin{i}(PluginBase):
    plugin_name = "plugin_{i}"

    def process(self, data_points):
        return {i}
""".format(i=i)
            with open(os.path.join(plugin_dir, "plugin_%d.py" % i), "w") as f:
                f.write(code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loaded = loader.load_all()

        assert loaded == 3

    def test_validate_plugin_class(self, plugin_dir):
        """Test plugin validation using operator.isCallable()."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class ValidPlugin(PluginBase):
    plugin_name = "valid"

    def process(self, data_points):
        return len(data_points)

    def activate(self):
        super(ValidPlugin, self).activate()
"""
        plugin_path = os.path.join(plugin_dir, "valid.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_module("valid", plugin_path)

        valid_plugin_class = PluginRegistry.get("valid")
        is_valid = loader.validate_plugin_class(valid_plugin_class)
        assert is_valid is True

    def test_validate_plugin_missing_process(self):
        """Test validation fails when process() is missing."""
        class BadPlugin(object):
            pass

        loader = PluginLoader()
        is_valid = loader.validate_plugin_class(BadPlugin)
        assert is_valid is False

    def test_instantiate_plugin(self, plugin_dir):
        """Test instantiating a registered plugin."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class InstPlugin(PluginBase):
    plugin_name = "inst_test"
    plugin_version = "1.0"

    def process(self, data_points):
        return data_points
"""
        plugin_path = os.path.join(plugin_dir, "inst.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_module("inst", plugin_path)

        inst = loader.instantiate_plugin("inst_test", {"param": "value"})
        assert inst is not None
        assert inst.config["param"] == "value"

    def test_instantiate_unknown_plugin_raises(self):
        """Test instantiating unknown plugin raises PlatformError."""
        loader = PluginLoader()
        with pytest.raises(PlatformError):
            loader.instantiate_plugin("does_not_exist")

    def test_activate_plugin(self, plugin_dir):
        """Test activating an instantiated plugin."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class ActivatePlugin(PluginBase):
    plugin_name = "activate_test"

    def process(self, data_points):
        return data_points
"""
        plugin_path = os.path.join(plugin_dir, "activate.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_module("activate", plugin_path)
        loader.instantiate_plugin("activate_test")

        result = loader.activate_plugin("activate_test")
        assert result is True

        # Verify activation
        active_plugins = loader.get_active_plugins()
        assert len(active_plugins) == 1
        assert active_plugins[0][0] == "activate_test"

    def test_activate_all(self, plugin_dir):
        """Test activating all instantiated plugins."""
        # Create two plugins
        for i in range(2):
            code = """
from src.automation.plugin_loader import PluginBase

class Plugin{i}(PluginBase):
    plugin_name = "multi_{i}"

    def process(self, data_points):
        return data_points
""".format(i=i)
            with open(os.path.join(plugin_dir, "multi_%d.py" % i), "w") as f:
                f.write(code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_all()
        loader.instantiate_all()

        activated = loader.activate_all()
        assert activated == 2

    def test_process_data(self, plugin_dir):
        """Test processing data through active plugins."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class ProcessPlugin(PluginBase):
    plugin_name = "processor"

    def process(self, data_points):
        return [dp * 2 for dp in data_points]
"""
        plugin_path = os.path.join(plugin_dir, "processor.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_module("processor", plugin_path)
        loader.instantiate_plugin("processor")
        loader.activate_plugin("processor")

        results = loader.process_data([1, 2, 3])
        assert results["processor"] == [2, 4, 6]

    def test_get_status(self, plugin_dir):
        """Test getting loader status."""
        plugin_code = """
from src.automation.plugin_loader import PluginBase

class StatusPlugin(PluginBase):
    plugin_name = "status_test"

    def process(self, data_points):
        return data_points
"""
        plugin_path = os.path.join(plugin_dir, "status.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        loader = PluginLoader(plugin_directory=plugin_dir)
        loader.load_module("status", plugin_path)
        loader.instantiate_plugin("status_test")
        loader.activate_plugin("status_test")

        status = loader.get_status()
        assert status["plugin_directory"] == plugin_dir
        assert status["loaded"] == 1
        assert status["registered"] == 1
        assert status["instantiated"] == 1
        assert status["active"] == 1


class TestFunctionIntrospection:
    """Test function/method attribute introspection."""

    def test_func_name_attribute(self):
        """Test accessing __name__ attribute (F1)."""
        def sample_function():
            pass

        assert sample_function.__name__ == "sample_function"

    def test_func_defaults_attribute(self):
        """Test accessing __defaults__ attribute (F2)."""
        def with_defaults(a, b=10, c="test"):
            pass

        assert with_defaults.__defaults__ == (10, "test")

    def test_func_closure_attribute(self):
        """Test accessing __closure__ attribute (F3)."""
        def make_counter():
            count = [0]

            def counter():
                count[0] += 1
                return count[0]

            return counter

        counter = make_counter()
        assert counter.__closure__ is not None
        assert len(counter.__closure__) == 1

    def test_im_func_attribute(self):
        """Test accessing method __func__ attribute (F4)."""
        class TestClass(object):
            def method(self):
                pass

        inst = TestClass()
        assert inst.method.__func__ == TestClass.method

    def test_im_self_attribute(self):
        """Test accessing method __self__ attribute (F5)."""
        class TestClass(object):
            def method(self):
                pass

        inst = TestClass()
        assert inst.method.__self__ is inst

    def test_im_class_attribute(self):
        """Test accessing method class via __self__.__class__ (F6)."""
        class TestClass(object):
            def method(self):
                pass

        inst = TestClass()
        assert inst.method.__self__.__class__ is TestClass
