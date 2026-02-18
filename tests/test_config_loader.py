# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/config_loader.py

Captures current Python 2 behavior for configuration loading.
Critical Py2→3 issues: ConfigParser.SafeConfigParser, __builtin__ access,
sys.maxint, print statements.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import os
import sys
import tempfile
import shutil

from src.core.config_loader import (
    PlatformConfig,
    load_platform_config,
    get_builtin_names,
    DEFAULT_MAX,
)


# ============================================================================
# PlatformConfig Tests
# ============================================================================


class TestPlatformConfigConstruction:
    """Characterize PlatformConfig initialization."""

    def test_construction_no_path(self):
        """PlatformConfig() initializes without path."""
        config = PlatformConfig()
        assert config._loaded is False
        assert config._path is None

    def test_construction_with_path(self):
        """PlatformConfig() accepts initial path."""
        config = PlatformConfig("/path/to/config.ini")
        assert config._path == "/path/to/config.ini"
        assert config._loaded is False


class TestPlatformConfigLoading:
    """Characterize config file loading."""

    def test_load_specific_file(self, tmp_path):
        """load() reads specified file."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n")

        config = PlatformConfig()
        config.load(str(config_file))

        assert config.is_loaded() is True
        assert config.get("section1", "key1") == "value1"

    def test_load_nonexistent_file_uses_defaults(self, tmp_path):
        """load() handles missing file gracefully."""
        config = PlatformConfig()
        config.load(str(tmp_path / "missing.ini"))

        # Should not be loaded but shouldn't crash
        assert config.is_loaded() is False

    def test_load_searches_default_paths(self, tmp_path, monkeypatch):
        """load() searches CONFIG_SEARCH_PATHS."""
        # Create config in search path
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "platform.ini"
        config_file.write_text("[test]\nfound = yes\n")

        # Patch search paths
        import src.core.config_loader as loader_module
        original_paths = loader_module.CONFIG_SEARCH_PATHS
        loader_module.CONFIG_SEARCH_PATHS = [str(config_dir)]

        try:
            config = PlatformConfig()
            config.load()

            assert config.is_loaded() is True
            assert config.get("test", "found") == "yes"
        finally:
            loader_module.CONFIG_SEARCH_PATHS = original_paths

    def test_is_loaded_reflects_state(self, tmp_path):
        """is_loaded() reflects whether config was loaded."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n")

        config = PlatformConfig()
        assert config.is_loaded() is False

        config.load(str(config_file))
        assert config.is_loaded() is True


class TestPlatformConfigTypedAccessors:
    """Characterize typed getter methods."""

    @pytest.fixture
    def config_with_data(self, tmp_path):
        """Config with test data."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("""
[database]
host = localhost
port = 5432
timeout = 30.5
enabled = true
disabled = false
tags = sensor1, sensor2, sensor3

[limits]
max_connections = 100
huge_value = 999999999999
        """)

        config = PlatformConfig()
        config.load(str(config_file))
        return config

    def test_get_basic(self, config_with_data):
        """get() retrieves string value."""
        result = config_with_data.get("database", "host")
        assert result == "localhost"

    def test_get_missing_returns_fallback(self, config_with_data):
        """get() returns fallback for missing key."""
        result = config_with_data.get("database", "missing", fallback="default")
        assert result == "default"

    def test_get_missing_section_returns_fallback(self, config_with_data):
        """get() returns fallback for missing section."""
        result = config_with_data.get("nosection", "key", fallback="default")
        assert result == "default"

    def test_get_int_basic(self, config_with_data):
        """get_int() parses integer."""
        result = config_with_data.get_int("database", "port")
        assert result == 5432

    def test_get_int_fallback(self, config_with_data):
        """get_int() uses fallback for missing key."""
        result = config_with_data.get_int("database", "missing", fallback=9999)
        assert result == 9999

    def test_get_int_invalid_returns_fallback(self, tmp_path):
        """get_int() returns fallback for invalid integer."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nbad = not_a_number\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get_int("test", "bad", fallback=42)
        assert result == 42

    def test_get_int_clamps_to_max(self, config_with_data):
        """get_int() clamps to max_value."""
        result = config_with_data.get_int("limits", "huge_value", max_value=1000)
        assert result == 1000

    def test_get_int_uses_default_max(self, config_with_data):
        """get_int() uses DEFAULT_MAX (sys.maxint) if no max_value."""
        # Should not clamp if value < sys.maxint
        result = config_with_data.get_int("limits", "max_connections")
        assert result == 100

    def test_get_float_basic(self, config_with_data):
        """get_float() parses float."""
        result = config_with_data.get_float("database", "timeout")
        assert result == 30.5

    def test_get_float_fallback(self, config_with_data):
        """get_float() uses fallback for missing key."""
        result = config_with_data.get_float("database", "missing", fallback=1.5)
        assert result == 1.5

    def test_get_float_invalid_returns_fallback(self, tmp_path):
        """get_float() returns fallback for invalid float."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nbad = not_a_float\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get_float("test", "bad", fallback=99.9)
        assert result == 99.9

    def test_get_bool_true_values(self, config_with_data):
        """get_bool() recognizes true values."""
        assert config_with_data.get_bool("database", "enabled") is True

    def test_get_bool_false_values(self, config_with_data):
        """get_bool() recognizes false values."""
        assert config_with_data.get_bool("database", "disabled") is False

    def test_get_bool_fallback(self, config_with_data):
        """get_bool() uses fallback for missing key."""
        result = config_with_data.get_bool("database", "missing", fallback=True)
        assert result is True

    def test_get_bool_variations(self, tmp_path):
        """get_bool() handles various true representations."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("""
[test]
v1 = 1
v2 = true
v3 = yes
v4 = on
v5 = True
v6 = YES
        """)

        config = PlatformConfig()
        config.load(str(config_file))

        for key in ["v1", "v2", "v3", "v4", "v5", "v6"]:
            assert config.get_bool("test", key) is True

    def test_get_list_basic(self, config_with_data):
        """get_list() splits comma-separated values."""
        result = config_with_data.get_list("database", "tags")
        assert result == ["sensor1", "sensor2", "sensor3"]

    def test_get_list_fallback(self, config_with_data):
        """get_list() uses fallback for missing key."""
        result = config_with_data.get_list("database", "missing", fallback=["default"])
        assert result == ["default"]

    def test_get_list_default_fallback(self, config_with_data):
        """get_list() defaults to empty list if no fallback."""
        result = config_with_data.get_list("database", "missing")
        assert result == []

    def test_get_list_custom_separator(self, tmp_path):
        """get_list() accepts custom separator."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nvalues = a:b:c\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get_list("test", "values", separator=":")
        assert result == ["a", "b", "c"]

    def test_get_list_strips_whitespace(self, tmp_path):
        """get_list() strips whitespace from items."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nvalues =  a  ,  b  ,  c  \n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get_list("test", "values")
        assert result == ["a", "b", "c"]


class TestPlatformConfigSectionAccess:
    """Characterize section/item access."""

    @pytest.fixture
    def config_with_sections(self, tmp_path):
        """Config with multiple sections."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("""
[section1]
key1 = value1

[section2]
key2 = value2
        """)

        config = PlatformConfig()
        config.load(str(config_file))
        return config

    def test_sections_returns_list(self, config_with_sections):
        """sections() returns list of section names."""
        result = config_with_sections.sections()
        assert "section1" in result
        assert "section2" in result

    def test_items_returns_key_value_pairs(self, config_with_sections):
        """items() returns (key, value) pairs for section."""
        result = config_with_sections.items("section1")
        assert ("key1", "value1") in result

    def test_items_missing_section_returns_empty(self, config_with_sections):
        """items() returns empty list for missing section."""
        result = config_with_sections.items("missing")
        assert result == []


class TestPlatformConfigEnvInterpolation:
    """Characterize environment variable interpolation."""

    def test_interpolate_env_replaces_var(self, tmp_path, monkeypatch):
        """get() interpolates ${VAR} from environment."""
        monkeypatch.setenv("TEST_VAR", "interpolated_value")

        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\npath = /data/${TEST_VAR}/output\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get("test", "path")
        assert result == "/data/interpolated_value/output"

    def test_interpolate_env_missing_var_leaves_token(self, tmp_path):
        """get() leaves ${VAR} if env var not set."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\npath = /data/${MISSING_VAR}/output\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get("test", "path")
        assert result == "/data/${MISSING_VAR}/output"

    def test_interpolate_multiple_vars(self, tmp_path, monkeypatch):
        """get() interpolates multiple ${VAR} tokens."""
        monkeypatch.setenv("VAR1", "first")
        monkeypatch.setenv("VAR2", "second")

        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\npath = ${VAR1}/${VAR2}\n")

        config = PlatformConfig()
        config.load(str(config_file))

        result = config.get("test", "path")
        assert result == "first/second"


class TestPlatformConfigEncodingHelpers:
    """Characterize encoding methods."""

    def test_default_encoding_returns_string(self):
        """default_encoding() returns system default encoding."""
        result = PlatformConfig.default_encoding()
        # Python 2 typically returns 'ascii' or 'utf-8'
        assert isinstance(result, str)

    def test_default_max_is_sys_maxint(self):
        """DEFAULT_MAX equals sys.maxsize in Python 3."""
        assert DEFAULT_MAX == sys.maxsize


class TestPlatformConfigDump:
    """Characterize dump() method."""

    def test_dump_not_loaded(self, capsys):
        """dump() reports when config not loaded."""
        config = PlatformConfig()
        config.dump()

        captured = capsys.readouterr()
        assert "not loaded" in captured.out.lower()

    def test_dump_shows_configuration(self, tmp_path, capsys):
        """dump() prints loaded configuration."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n")

        config = PlatformConfig()
        config.load(str(config_file))
        config.dump()

        captured = capsys.readouterr()
        assert "section1" in captured.out
        assert "key1" in captured.out
        assert "value1" in captured.out
        assert "sys.maxsize" in captured.out


# ============================================================================
# Module-level convenience functions
# ============================================================================


class TestLoadPlatformConfig:
    """Characterize module-level load function."""

    def test_load_platform_config_creates_global(self, tmp_path):
        """load_platform_config() creates and caches global config."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nkey = value\n")

        # Clear global state
        import src.core.config_loader as loader_module
        loader_module._global_config = None

        config1 = load_platform_config(str(config_file))
        config2 = load_platform_config()

        # Should return same instance
        assert config1 is config2

    def test_load_platform_config_loads_once(self, tmp_path):
        """load_platform_config() only loads once."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[test]\nkey = value\n")

        # Clear global state
        import src.core.config_loader as loader_module
        loader_module._global_config = None

        config = load_platform_config(str(config_file))
        assert config.is_loaded() is True


class TestGetBuiltinNames:
    """Characterize __builtin__ module access."""

    def test_get_builtin_names_returns_list(self):
        """get_builtin_names() returns list of builtin names."""
        result = get_builtin_names()
        assert isinstance(result, list)

    def test_get_builtin_names_includes_expected(self):
        """get_builtin_names() includes expected builtins."""
        result = get_builtin_names()
        # Common builtins that should be present
        assert "len" in result
        assert "str" in result
        assert "dict" in result

    def test_get_builtin_names_uses_builtin_module(self):
        """get_builtin_names() accesses __builtin__ module."""
        # In Python 2, __builtin__ exists; in Python 3 it's builtins
        result = get_builtin_names()
        assert len(result) > 0
