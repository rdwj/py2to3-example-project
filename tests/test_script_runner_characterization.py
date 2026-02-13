# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/script_runner.py

Captures pre-migration behavior of:
- ScriptResult data holder
- ScriptContext sandboxed namespace with __builtin__
- Tuple parameter unpacking (PEP 3113, removed in Py3)
- exec statement form (became function in Py3)
- execfile() (removed in Py3)
- commands.getoutput() (removed in Py3)
- operator.isMappingType/isSequenceType/sequenceIncludes (removed)
- dict.iteritems()
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.automation.script_runner import (
    ScriptResult, ScriptContext, ScriptRunner,
    _unpack_script_bounds, _format_param_pair,
    ALLOWED_BUILTINS,
)
from src.core.exceptions import PlatformError


# ---------------------------------------------------------------------------
# ScriptResult
# ---------------------------------------------------------------------------

class TestScriptResult:
    """Characterize script result data holder."""

    def test_initial_state(self):
        """Captures: default state after construction."""
        result = ScriptResult("test.py")
        assert result.script_name == "test.py"
        assert result.success is False
        assert result.return_value is None
        assert result.output == ""
        assert result.error_message is None
        assert result.elapsed_seconds == 0.0

    def test_repr_ok(self):
        """Captures: repr shows OK status."""
        r = ScriptResult("test.py")
        r.success = True
        r.elapsed_seconds = 1.5
        assert "OK" in repr(r)
        assert "1.50s" in repr(r)

    def test_repr_failed(self):
        """Captures: repr shows FAILED status."""
        r = ScriptResult("test.py")
        assert "FAILED" in repr(r)


# ---------------------------------------------------------------------------
# ScriptContext
# ---------------------------------------------------------------------------

class TestScriptContext:
    """Characterize the sandboxed execution namespace."""

    @pytest.mark.py2_behavior
    def test_namespace_has_safe_builtins(self):
        """Captures: namespace __builtins__ is a restricted dict, not the module.
        Uses __builtin__ module (renamed builtins in Py3)."""
        ctx = ScriptContext("test")
        builtins = ctx.namespace["__builtins__"]
        assert isinstance(builtins, dict)
        assert "len" in builtins
        assert "range" in builtins

    def test_namespace_has_log_function(self):
        """Captures: 'log' function is injected into namespace."""
        ctx = ScriptContext("test")
        assert "log" in ctx.namespace
        assert callable(ctx.namespace["log"])

    def test_log_captures_output(self):
        """Captures: log() calls accumulate in output."""
        ctx = ScriptContext("test")
        ctx.namespace["log"]("hello", "world")
        output = ctx.get_output()
        assert "hello world" in output

    @pytest.mark.py2_behavior
    def test_platform_api_via_iteritems(self):
        """Captures: platform_api injected via dict.iteritems() (Py2)."""
        api = {"read_sensor": lambda x: x, "write_tag": lambda x, y: None}
        ctx = ScriptContext("test", platform_api=api)
        assert "read_sensor" in ctx.namespace
        assert "write_tag" in ctx.namespace

    def test_variables_injected(self):
        """Captures: custom variables added to namespace."""
        ctx = ScriptContext("test", variables={"x": 42, "name": "test"})
        assert ctx.get_variable("x") == 42
        assert ctx.get_variable("name") == "test"

    def test_get_variable_default(self):
        """Captures: missing variable returns default."""
        ctx = ScriptContext("test")
        assert ctx.get_variable("missing", "default") == "default"


# ---------------------------------------------------------------------------
# Tuple parameter unpacking
# ---------------------------------------------------------------------------

class TestTupleParameterUnpacking:
    """Characterize tuple parameter unpacking (PEP 3113)."""

    @pytest.mark.py2_behavior
    def test_unpack_script_bounds(self):
        """Captures: _unpack_script_bounds((min, max)) uses tuple unpacking.
        Removed in Py3; must be rewritten as def f(bounds): min, max = bounds."""
        result = _unpack_script_bounds((0, 100))
        assert result == (0, 100)

    @pytest.mark.py2_behavior
    def test_unpack_script_bounds_invalid(self):
        """Captures: min > max raises PlatformError."""
        with pytest.raises(PlatformError, match="Invalid bounds"):
            _unpack_script_bounds((100, 0))

    @pytest.mark.py2_behavior
    def test_format_param_pair(self):
        """Captures: _format_param_pair((name, value)) uses tuple unpacking."""
        result = _format_param_pair(("timeout", 30))
        assert result == "timeout=30"


# ---------------------------------------------------------------------------
# ScriptRunner
# ---------------------------------------------------------------------------

class TestScriptRunner:
    """Characterize the script execution engine."""

    @pytest.fixture
    def runner(self, tmp_path):
        return ScriptRunner(script_directory=str(tmp_path), platform_api={})

    @pytest.mark.py2_behavior
    def test_execute_string_simple(self, runner):
        """Captures: exec statement form (Py2: exec code in namespace).
        Py3: exec(code, namespace)."""
        result = runner.execute_string("result = 42", "simple_test")
        assert result.success is True
        assert result.return_value == 42

    @pytest.mark.py2_behavior
    def test_execute_string_with_variables(self, runner):
        """Captures: variables available in exec namespace."""
        code = "result = x + y"
        result = runner.execute_string(code, "var_test", variables={"x": 10, "y": 32})
        assert result.success is True
        assert result.return_value == 42

    def test_execute_string_syntax_error(self, runner):
        """Captures: syntax error captured in result.error_message."""
        result = runner.execute_string("def :", "bad_syntax")
        assert result.success is False
        assert result.error_message is not None
        assert "SyntaxError" in result.error_message

    def test_execute_string_runtime_error(self, runner):
        """Captures: runtime error captured in result."""
        result = runner.execute_string("result = 1/0", "div_zero")
        assert result.success is False
        assert "ZeroDivisionError" in result.error_message

    def test_execute_string_uses_log(self, runner):
        """Captures: log function accessible from exec'd code."""
        code = "log('hello from script'); result = True"
        result = runner.execute_string(code, "log_test")
        assert result.success is True
        assert "hello from script" in result.output

    @pytest.mark.py2_behavior
    def test_execute_file(self, runner, tmp_path):
        """Captures: execfile() for file-based execution (removed in Py3)."""
        script = tmp_path / "test_script.py"
        script.write_text("result = 'from_file'")
        result = runner.execute_file("test_script.py")
        assert result.success is True
        assert result.return_value == "from_file"

    def test_execute_file_missing(self, runner):
        """Captures: missing script file raises PlatformError."""
        with pytest.raises(PlatformError, match="Script not found"):
            runner.execute_file("nonexistent.py")

    @pytest.mark.py2_behavior
    def test_validate_arguments_mapping(self, runner):
        """Captures: operator.isMappingType() for dict validation (removed Py3)."""
        assert runner.validate_arguments({"key": "value"}) is True

    @pytest.mark.py2_behavior
    def test_validate_arguments_sequence(self, runner):
        """Captures: operator.isSequenceType() for list validation (removed Py3)."""
        assert runner.validate_arguments([1, 2, 3]) is True

    @pytest.mark.py2_behavior
    def test_check_allowed_command(self, runner):
        """Captures: operator.sequenceIncludes() (removed in Py3)."""
        allowed = ["ls", "cat", "grep"]
        assert runner.check_allowed_command("ls", allowed) is True
        assert runner.check_allowed_command("rm", allowed) is False

    @pytest.mark.py2_behavior
    def test_validate_bounds(self, runner):
        """Captures: validate_bounds delegates to _unpack_script_bounds."""
        result = runner.validate_bounds([(0, 100), (10, 50)])
        assert result == [(0, 100), (10, 50)]

    @pytest.mark.py2_behavior
    def test_format_parameters(self, runner):
        """Captures: format_parameters uses dict.iteritems() and tuple unpacking."""
        result = runner.format_parameters({"timeout": 30})
        assert "timeout=30" in result

    def test_get_execution_stats(self, runner):
        """Captures: stats structure after some executions."""
        runner.execute_string("result = 1", "s1")
        runner.execute_string("result = 2", "s2")
        stats = runner.get_execution_stats()
        assert stats["total_executions"] == 2

    def test_load_and_cache_script(self, runner, tmp_path):
        """Captures: load_script_file reads and caches source code."""
        script = tmp_path / "cached.py"
        script.write_text("x = 1")
        source = runner.load_script_file("cached.py")
        assert "x = 1" in source
        # Second call returns cached version
        source2 = runner.load_script_file("cached.py")
        assert source == source2

    def test_clear_cache(self, runner, tmp_path):
        """Captures: clear_cache empties the loaded scripts dict."""
        script = tmp_path / "temp.py"
        script.write_text("pass")
        runner.load_script_file("temp.py")
        runner.clear_cache()
        assert runner.get_execution_stats()["cached_scripts"] == 0
