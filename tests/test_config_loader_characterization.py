# -*- coding: utf-8 -*-
"""
Characterization tests for src/core/config_loader.py

Captures pre-migration behavior of:
- PlatformConfig with ConfigParser.SafeConfigParser
- Typed accessors (get, get_int, get_float, get_bool, get_list)
- Environment variable interpolation (${VAR})
- sys.maxint as DEFAULT_MAX
- __builtin__ module (renamed builtins in Py3)
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.core.config_loader import (
    PlatformConfig, load_platform_config, get_builtin_names,
    DEFAULT_MAX,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path):
    """Create a temporary config file."""
    content = """\
[database]
host = localhost
port = 5432
timeout = 30
debug = true
replicas = db1, db2, db3

[sensors]
poll_interval = 1.5
max_reading = 999999
encoding = utf-8

[env_test]
home = ${HOME}
missing = ${NONEXISTENT_VAR_12345}

[email_lists]
ops = alice@plant.local, bob@plant.local
"""
    p = tmp_path / "platform.ini"
    p.write_text(content)
    return str(p)


@pytest.fixture
def config(config_file):
    """Return a loaded PlatformConfig."""
    cfg = PlatformConfig(config_file)
    cfg.load()
    return cfg


# ---------------------------------------------------------------------------
# PlatformConfig loading
# ---------------------------------------------------------------------------

class TestPlatformConfigLoading:
    """Characterize config file loading."""

    def test_load_from_explicit_path(self, config):
        """Captures: load from a specified path."""
        assert config.is_loaded() is True

    def test_load_nonexistent_file(self, tmp_path):
        """Captures: loading from nonexistent path uses defaults (no crash)."""
        cfg = PlatformConfig(str(tmp_path / "no_such_file.ini"))
        cfg.load()
        assert cfg.is_loaded() is False

    def test_sections(self, config):
        """Captures: sections() returns list of section names."""
        sections = config.sections()
        assert "database" in sections
        assert "sensors" in sections

    def test_items(self, config):
        """Captures: items(section) returns key-value pairs."""
        items = config.items("database")
        keys = [k for k, v in items]
        assert "host" in keys
        assert "port" in keys


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------

class TestPlatformConfigAccessors:
    """Characterize typed configuration value access."""

    def test_get_string(self, config):
        """Captures: get returns string value."""
        assert config.get("database", "host") == "localhost"

    def test_get_missing_key_fallback(self, config):
        """Captures: missing key returns fallback value."""
        assert config.get("database", "missing_key", "default") == "default"

    def test_get_missing_section_fallback(self, config):
        """Captures: missing section returns fallback value."""
        assert config.get("nonexistent", "key", "default") == "default"

    def test_get_int(self, config):
        """Captures: get_int parses integer value."""
        assert config.get_int("database", "port") == 5432

    def test_get_int_bad_value(self, config):
        """Captures: get_int with non-numeric returns fallback."""
        assert config.get_int("database", "host", fallback=-1) == -1

    @pytest.mark.py2_behavior
    def test_get_int_clamped_to_max(self, config):
        """Captures: value exceeding max_value is clamped.
        DEFAULT_MAX uses sys.maxint (removed in Py3; use sys.maxsize)."""
        result = config.get_int("sensors", "max_reading", max_value=1000)
        assert result == 1000

    def test_get_float(self, config):
        """Captures: get_float parses float value."""
        assert config.get_float("sensors", "poll_interval") == 1.5

    def test_get_float_missing(self, config):
        """Captures: missing key returns float fallback."""
        assert config.get_float("sensors", "missing", fallback=0.0) == 0.0

    def test_get_bool_true(self, config):
        """Captures: 'true' parsed as boolean True."""
        assert config.get_bool("database", "debug") is True

    def test_get_bool_false(self, config):
        """Captures: missing/unset parsed as fallback."""
        assert config.get_bool("database", "missing", fallback=False) is False

    def test_get_list(self, config):
        """Captures: comma-separated value split into list."""
        result = config.get_list("database", "replicas")
        assert result == ["db1", "db2", "db3"]

    def test_get_list_missing_returns_empty(self, config):
        """Captures: missing key returns empty list."""
        assert config.get_list("database", "missing") == []


# ---------------------------------------------------------------------------
# Environment variable interpolation
# ---------------------------------------------------------------------------

class TestEnvironmentInterpolation:
    """Characterize ${VAR} substitution in config values."""

    def test_interpolation_existing_var(self, config):
        """Captures: ${HOME} replaced with actual environment variable."""
        home = config.get("env_test", "home")
        assert home == os.environ.get("HOME", "${HOME}")

    def test_interpolation_missing_var(self, config):
        """Captures: ${NONEXISTENT_VAR_12345} left as-is when unset."""
        value = config.get("env_test", "missing")
        assert "${NONEXISTENT_VAR_12345}" in value

    def test_no_interpolation_needed(self, config):
        """Captures: values without ${} returned unchanged."""
        assert config.get("database", "host") == "localhost"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestModuleLevelHelpers:
    """Characterize module-level convenience functions."""

    @pytest.mark.py2_behavior
    def test_default_max_is_sys_maxsize(self):
        """Captures: DEFAULT_MAX = sys.maxsize (was sys.maxint in Py2)."""
        assert DEFAULT_MAX == sys.maxsize
        assert DEFAULT_MAX > 0

    @pytest.mark.py2_behavior
    def test_get_builtin_names(self):
        """Captures: get_builtin_names uses __builtin__ module.
        Renamed to builtins in Py3."""
        names = get_builtin_names()
        assert isinstance(names, list)
        assert "len" in names
        assert "range" in names

    def test_default_encoding(self):
        """Captures: default_encoding returns sys.getdefaultencoding()."""
        cfg = PlatformConfig()
        enc = cfg.default_encoding()
        assert enc in ("ascii", "utf-8")
