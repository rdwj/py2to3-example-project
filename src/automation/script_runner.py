# -*- coding: utf-8 -*-
"""
Dynamic script execution engine for the Legacy Industrial Data Platform.

Provides a sandboxed environment for running automation scripts that
perform data collection, transformation, and reporting.  Plant engineers
write short Python scripts loaded and executed dynamically with access
to a controlled set of platform APIs.

Uses ``exec`` (statement form), ``execfile()``, and
``commands.getoutput()`` -- all changed or removed in Python 3.
"""

import os
import sys
import time
import operator
import commands

from core.exceptions import PlatformError

SCRIPT_TIMEOUT_DEFAULT = 300
ALLOWED_BUILTINS = [
    "len", "range", "xrange", "str", "int", "float", "list", "dict",
    "tuple", "set", "sorted", "enumerate", "zip", "map", "filter",
    "min", "max", "sum", "abs", "round", "isinstance", "hasattr",
    "getattr", "setattr", "True", "False", "None",
]


class ScriptResult(object):
    """Captures the outcome of a script execution."""

    def __init__(self, script_name):
        self.script_name = script_name
        self.success = False
        self.return_value = None
        self.output = ""
        self.error_message = None
        self.elapsed_seconds = 0.0

    def __repr__(self):
        status = "OK" if self.success else "FAILED"
        return "ScriptResult(%r, %s, %.2fs)" % (self.script_name, status, self.elapsed_seconds)


class ScriptContext(object):
    """Sandboxed namespace for script execution."""

    def __init__(self, script_name, platform_api=None, variables=None):
        self.script_name = script_name
        self.namespace = {}
        self._platform_api = platform_api or {}
        self._output_lines = []
        self._build_namespace(variables)

    def _build_namespace(self, variables):
        import __builtin__
        safe = {}
        for name in ALLOWED_BUILTINS:
            if hasattr(__builtin__, name):
                safe[name] = getattr(__builtin__, name)
        self.namespace["__builtins__"] = safe
        self.namespace["__name__"] = "automation_script"
        for k, v in self._platform_api.iteritems():
            self.namespace[k] = v
        self.namespace["log"] = self._log
        self.namespace["get_timestamp"] = time.time
        if variables is not None:
            for k, v in variables.iteritems():
                self.namespace[k] = v

    def _log(self, *args):
        self._output_lines.append(" ".join(str(a) for a in args))

    def get_output(self):
        return "\n".join(self._output_lines)

    def get_variable(self, name, default=None):
        return self.namespace.get(name, default)


def _unpack_script_bounds((min_val, max_val)):
    """Validate range bounds.  Tuple parameter unpacking (A8) was
    removed in Python 3 (PEP 3113)."""
    if min_val > max_val:
        raise PlatformError("Invalid bounds: min %s > max %s" % (min_val, max_val))
    return min_val, max_val


def _format_param_pair((name, value)):
    """Format a name-value pair for logging (A8)."""
    return "%s=%r" % (name, value)


class ScriptRunner(object):
    """Loads, validates, and executes automation scripts within a
    sandboxed context for sensor reading, derived-value computation,
    alarm triggering, and shift report generation."""

    def __init__(self, script_directory=None, platform_api=None,
                 timeout=SCRIPT_TIMEOUT_DEFAULT):
        self.script_directory = script_directory or "/opt/platform/scripts"
        self.platform_api = platform_api or {}
        self.timeout = timeout
        self._execution_count = 0
        self._loaded_scripts = {}
        print "ScriptRunner initialised, dir: %s" % self.script_directory

    def validate_arguments(self, args):
        """Uses ``operator.isSequenceType()`` (H3) and
        ``operator.isMappingType()`` (H4), both removed in Py3."""
        if operator.isMappingType(args):
            return True
        if operator.isSequenceType(args):
            return True
        print "WARNING: bad argument type: %s" % type(args)
        return False

    def check_allowed_command(self, cmd_name, allowed):
        """Uses ``operator.sequenceIncludes()`` (H2), removed in Py3."""
        return operator.sequenceIncludes(allowed, cmd_name)

    def load_script_file(self, filename):
        if filename in self._loaded_scripts:
            return self._loaded_scripts[filename]
        filepath = os.path.join(self.script_directory, filename)
        if not os.path.isfile(filepath):
            raise PlatformError("Script not found: %s" % filepath)
        fh = open(filepath, "r")
        try:
            source = fh.read()
        finally:
            fh.close()
        self._loaded_scripts[filename] = source
        print "Loaded script: %s (%d bytes)" % (filename, len(source))
        return source

    def execute_string(self, script_code, script_name="<inline>", variables=None):
        """Execute code string via ``exec`` statement (A2).  In Py3
        ``exec`` became a function."""
        ctx = ScriptContext(script_name, self.platform_api, variables)
        result = ScriptResult(script_name)
        t0 = time.time()
        print "Executing inline script %r" % script_name
        try:
            exec script_code in ctx.namespace
            result.success = True
            result.return_value = ctx.get_variable("result")
        except PlatformError, e:
            result.error_message = "Platform error: %s" % str(e)
            print "Script %r failed: %s" % (script_name, result.error_message)
        except Exception, e:
            result.error_message = "%s: %s" % (type(e).__name__, e)
            print "Script %r failed: %s" % (script_name, result.error_message)
        result.output = ctx.get_output()
        result.elapsed_seconds = time.time() - t0
        self._execution_count += 1
        return result

    def execute_file(self, filename, variables=None):
        """Execute via ``execfile()`` (A19), removed in Py3."""
        filepath = os.path.join(self.script_directory, filename)
        if not os.path.isfile(filepath):
            raise PlatformError("Script not found: %s" % filepath)
        ctx = ScriptContext(filename, self.platform_api, variables)
        result = ScriptResult(filename)
        t0 = time.time()
        print "Executing script file %r" % filepath
        try:
            execfile(filepath, ctx.namespace)
            result.success = True
            result.return_value = ctx.get_variable("result")
        except PlatformError, e:
            result.error_message = "Platform error: %s" % str(e)
        except Exception, e:
            result.error_message = "%s: %s" % (type(e).__name__, e)
            print "Script %r failed: %s" % (filename, result.error_message)
        result.output = ctx.get_output()
        result.elapsed_seconds = time.time() - t0
        self._execution_count += 1
        return result

    def run_shell_command(self, command, allowed_commands=None):
        """Execute via ``commands.getoutput()`` (D14), removed in Py3."""
        if allowed_commands is not None:
            cmd_name = command.split()[0] if command.strip() else ""
            if not self.check_allowed_command(cmd_name, allowed_commands):
                raise PlatformError("Command %r not allowed" % cmd_name)
        print "Running shell command: %s" % command
        return commands.getoutput(command)

    def validate_bounds(self, bounds_list):
        return [_unpack_script_bounds(b) for b in bounds_list]

    def format_parameters(self, param_dict):
        return ", ".join(_format_param_pair(item) for item in param_dict.iteritems())

    def get_execution_stats(self):
        return {"total_executions": self._execution_count,
                "cached_scripts": len(self._loaded_scripts),
                "script_directory": self.script_directory}

    def clear_cache(self):
        count = len(self._loaded_scripts)
        self._loaded_scripts.clear()
        print "Cleared %d cached scripts" % count
