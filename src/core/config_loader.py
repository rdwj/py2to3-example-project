# -*- coding: utf-8 -*-
"""
Configuration loader for the Legacy Industrial Data Platform.

Reads ``config/platform.ini`` via ``ConfigParser.SafeConfigParser``
and exposes a dict-like interface to the rest of the system.  Also
provides helpers for environment-variable interpolation and sanity
checking of required keys.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import configparser
import builtins

# Default ceiling for any numeric configuration value that the caller
# does not explicitly cap.  ``sys.maxint`` is the largest positive
# integer on the platform (2**31-1 or 2**63-1); it does not exist in
# Python 3 which has arbitrary-precision ints and uses ``sys.maxsize``.
DEFAULT_MAX = sys.maxsize

# Default config file search paths, in priority order
CONFIG_SEARCH_PATHS = [
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "config"),
    "/etc/platform",
    "/opt/platform/config",
]


class PlatformConfig(object):
    """Thin wrapper around ``SafeConfigParser`` with convenience methods
    for typed access and environment-variable substitution."""

    def __init__(self, config_path=None):
        self._parser = configparser.ConfigParser()
        self._path = config_path
        self._loaded = False

    # ---------------------------------------------------------------
    # Loading
    # ---------------------------------------------------------------

    def load(self, path=None):
        """Read the INI file from *path* or search the default locations."""
        if path is not None:
            self._path = path

        if self._path and os.path.isfile(self._path):
            print("Loading config from", self._path)
            self._parser.read(self._path)
            self._loaded = True
            return

        for search_dir in CONFIG_SEARCH_PATHS:
            candidate = os.path.join(search_dir, "platform.ini")
            if os.path.isfile(candidate):
                print("Found config at", candidate)
                self._parser.read(candidate)
                self._path = candidate
                self._loaded = True
                return

        print("WARNING: no configuration file found; using defaults")

    def is_loaded(self):
        return self._loaded

    # ---------------------------------------------------------------
    # Typed accessors
    # ---------------------------------------------------------------

    def get(self, section, key, fallback=None):
        try:
            value = self._parser.get(section, key)
            return self._interpolate_env(value)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_int(self, section, key, fallback=0, max_value=None):
        raw = self.get(section, key)
        if raw is None:
            return fallback
        try:
            value = int(raw)
        except (ValueError, TypeError):
            print("Config warning: bad integer for [%s] %s = %r" % (section, key, raw))
            return fallback

        ceiling = max_value if max_value is not None else DEFAULT_MAX
        if value > ceiling:
            print("Config warning: clamping [%s] %s to max %d" % (section, key, ceiling))
            value = ceiling
        return value

    def get_float(self, section, key, fallback=0.0):
        raw = self.get(section, key)
        if raw is None:
            return fallback
        try:
            return float(raw)
        except (ValueError, TypeError):
            print("Config warning: bad float for [%s] %s = %r" % (section, key, raw))
            return fallback

    def get_bool(self, section, key, fallback=False):
        raw = self.get(section, key)
        if raw is None:
            return fallback
        return raw.strip().lower() in ("1", "true", "yes", "on")

    def get_list(self, section, key, separator=",", fallback=None):
        raw = self.get(section, key)
        if raw is None:
            return fallback if fallback is not None else []
        return [item.strip() for item in raw.split(separator) if item.strip()]

    def sections(self):
        return self._parser.sections()

    def items(self, section):
        try:
            return self._parser.items(section)
        except configparser.NoSectionError:
            return []

    # ---------------------------------------------------------------
    # Environment variable interpolation
    # ---------------------------------------------------------------

    @staticmethod
    def _interpolate_env(value):
        """Replace ``${VAR}`` tokens with the corresponding environment
        variable, or leave the token in place if the variable is unset."""
        if "${" not in value:
            return value
        import re
        def _replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return re.sub(r"\$\{([^}]+)\}", _replace, value)

    # ---------------------------------------------------------------
    # Encoding helpers
    # ---------------------------------------------------------------

    @staticmethod
    def default_encoding():
        """Return the system default encoding.

        In Python 2 this is almost always ``'ascii'`` unless someone
        called ``sys.setdefaultencoding()`` via a sitecustomize hack.
        Python 3 defaults to ``'utf-8'``.
        """
        return sys.getdefaultencoding()

    # ---------------------------------------------------------------
    # Debug dump
    # ---------------------------------------------------------------

    def dump(self):
        """Print the loaded configuration to stdout for diagnostics."""
        if not self._loaded:
            print("Config not loaded yet")
            return
        print("--- Platform Configuration ---")
        print("Source:", self._path)
        print("Default encoding:", self.default_encoding())
        print("sys.maxsize:", DEFAULT_MAX)
        for section in self._parser.sections():
            print("[%s]" % section)
            for key, value in self._parser.items(section):
                print("  %s = %s" % (key, value))
        print("--- End Configuration ---")


# -------------------------------------------------------------------
# Module-level convenience: load once and share
# -------------------------------------------------------------------

_global_config = None


def load_platform_config(path=None):
    """Load (or return the already-loaded) platform configuration."""
    global _global_config
    if _global_config is None:
        _global_config = PlatformConfig(path)
        _global_config.load(path)
    return _global_config


def get_builtin_names():
    """Return the list of builtin names via the ``__builtin__`` module.

    In Python 3 the module was renamed to ``builtins``."""
    return dir(builtins)
