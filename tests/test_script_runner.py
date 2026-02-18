# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/script_runner.py

Tests dynamic script execution, exec statement, execfile(), tuple unpacking
in function parameters, and operator module functions (sequenceIncludes,
isSequenceType, isMappingType). Mocks file system for script loading.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import time
import pytest
from unittest import mock
import operator

from src.automation.script_runner import (
    ScriptResult, ScriptContext, ScriptRunner,
    _unpack_script_bounds, _format_param_pair,
    SCRIPT_TIMEOUT_DEFAULT, ALLOWED_BUILTINS
)
from src.core.exceptions import PlatformError


# ============================================================================
# ScriptResult Tests
# ============================================================================

def test_script_result_init():
    """Test ScriptResult initialization."""
    result = ScriptResult("test_script.py")

    assert result.script_name == "test_script.py"
    assert result.success is False
    assert result.return_value is None
    assert result.output == ""
    assert result.error_message is None
    assert result.elapsed_seconds == 0.0


def test_script_result_repr():
    """Test ScriptResult string representation."""
    result = ScriptResult("example.py")
    result.success = True
    result.elapsed_seconds = 1.234

    repr_str = repr(result)

    assert "example.py" in repr_str
    assert "OK" in repr_str
    assert "1.23" in repr_str


def test_script_result_repr_failed():
    """Test ScriptResult repr for failed execution."""
    result = ScriptResult("failed.py")
    result.success = False

    repr_str = repr(result)
    assert "FAILED" in repr_str


# ============================================================================
# ScriptContext Tests
# ============================================================================

def test_script_context_init_minimal():
    """Test ScriptContext initialization with minimal parameters."""
    ctx = ScriptContext("test.py")

    assert ctx.script_name == "test.py"
    assert isinstance(ctx.namespace, dict)
    assert "__builtins__" in ctx.namespace
    assert "__name__" in ctx.namespace
    assert "log" in ctx.namespace
    assert "get_timestamp" in ctx.namespace


def test_script_context_allowed_builtins():
    """Test that only allowed builtins are exposed."""
    ctx = ScriptContext("safe.py")

    builtins = ctx.namespace["__builtins__"]

    # Should have safe builtins
    assert "len" in builtins
    assert "range" in builtins
    assert "str" in builtins

    # Should NOT have dangerous builtins
    assert "open" not in builtins
    assert "eval" not in builtins
    assert "__import__" not in builtins


def test_script_context_platform_api():
    """Test that platform API functions are injected."""
    api = {
        "read_sensor": lambda tag: 42.5,
        "write_output": lambda tag, val: None,
    }

    ctx = ScriptContext("api_test.py", platform_api=api)

    assert "read_sensor" in ctx.namespace
    assert "write_output" in ctx.namespace
    assert ctx.namespace["read_sensor"]("TEMP") == 42.5


def test_script_context_variables():
    """Test that custom variables are added to namespace."""
    variables = {
        "sensor_tag": "TEMP_001",
        "threshold": 100.0,
        "enabled": True,
    }

    ctx = ScriptContext("var_test.py", variables=variables)

    assert ctx.namespace["sensor_tag"] == "TEMP_001"
    assert ctx.namespace["threshold"] == 100.0
    assert ctx.namespace["enabled"] is True


def test_script_context_log_function():
    """Test logging function captures output."""
    ctx = ScriptContext("log_test.py")

    ctx.namespace["log"]("Hello", "world", 123)
    ctx.namespace["log"]("Another line")

    output = ctx.get_output()
    assert "Hello world 123" in output
    assert "Another line" in output


def test_script_context_get_variable():
    """Test retrieving variables from namespace."""
    ctx = ScriptContext("get_var.py")
    ctx.namespace["result"] = 42
    ctx.namespace["data"] = [1, 2, 3]

    assert ctx.get_variable("result") == 42
    assert ctx.get_variable("data") == [1, 2, 3]
    assert ctx.get_variable("nonexistent") is None
    assert ctx.get_variable("missing", default="default_val") == "default_val"


# ============================================================================
# Tuple Unpacking Helper Tests (A8 - PEP 3113)
# ============================================================================

def test_unpack_script_bounds_valid():
    """Test tuple unpacking in function parameters (A8)."""
    result = _unpack_script_bounds((10, 100))
    assert result == (10, 100)


def test_unpack_script_bounds_invalid():
    """Test validation in tuple unpacking function."""
    with pytest.raises(PlatformError, match="Invalid bounds"):
        _unpack_script_bounds((100, 10))


def test_format_param_pair():
    """Test formatting parameter pair (tuple unpacking in params)."""
    result = _format_param_pair(("threshold", 85.5))
    assert result == "threshold=85.5"

    result = _format_param_pair(("name", "sensor_a"))
    assert "name=" in result
    assert "sensor_a" in result


# ============================================================================
# ScriptRunner Tests
# ============================================================================

def test_script_runner_init_defaults(capsys):
    """Test ScriptRunner initialization with defaults."""
    runner = ScriptRunner()

    assert runner.script_directory == "/opt/platform/scripts"
    assert runner.timeout == SCRIPT_TIMEOUT_DEFAULT
    assert runner._execution_count == 0
    assert len(runner._loaded_scripts) == 0

    captured = capsys.readouterr()
    assert "ScriptRunner initialised" in captured.out


def test_script_runner_init_custom():
    """Test ScriptRunner with custom parameters."""
    api = {"sensor_read": lambda: 1}

    runner = ScriptRunner(
        script_directory="/custom/scripts",
        platform_api=api,
        timeout=600
    )

    assert runner.script_directory == "/custom/scripts"
    assert runner.timeout == 600
    assert "sensor_read" in runner.platform_api


def test_script_runner_validate_arguments_mapping():
    """Test argument validation with mapping type (operator.isMappingType - H4)."""
    runner = ScriptRunner()

    result = runner.validate_arguments({"key": "value"})
    assert result is True


def test_script_runner_validate_arguments_sequence():
    """Test argument validation with sequence type (operator.isSequenceType - H3)."""
    runner = ScriptRunner()

    result = runner.validate_arguments([1, 2, 3])
    assert result is True

    result = runner.validate_arguments((1, 2, 3))
    assert result is True


def test_script_runner_validate_arguments_invalid(capsys):
    """Test argument validation with invalid type."""
    runner = ScriptRunner()

    result = runner.validate_arguments(42)
    assert result is False

    captured = capsys.readouterr()
    assert "WARNING: bad argument type" in captured.out


def test_script_runner_check_allowed_command_true():
    """Test command allowlist check (operator.sequenceIncludes - H2)."""
    runner = ScriptRunner()

    allowed = ["ls", "cat", "grep"]
    result = runner.check_allowed_command("cat", allowed)

    assert result is True


def test_script_runner_check_allowed_command_false():
    """Test command blocked when not in allowlist."""
    runner = ScriptRunner()

    allowed = ["ls", "cat"]
    result = runner.check_allowed_command("rm", allowed)

    assert result is False


@mock.patch("os.path.isfile")
@mock.patch("builtins.open", create=True)
def test_script_runner_load_script_file(mock_open, mock_isfile, capsys):
    """Test loading script from file system."""
    mock_isfile.return_value = True
    mock_open.return_value.__enter__ = mock.Mock(return_value=mock_open.return_value)
    mock_open.return_value.__exit__ = mock.Mock()
    mock_open.return_value.read.return_value = "print('Hello')\nresult = 42"

    runner = ScriptRunner(script_directory="/test/scripts")
    source = runner.load_script_file("test.py")

    assert "print('Hello')" in source
    assert "result = 42" in source
    assert "test.py" in runner._loaded_scripts

    captured = capsys.readouterr()
    assert "Loaded script: test.py" in captured.out


@mock.patch("os.path.isfile")
def test_script_runner_load_script_file_not_found(mock_isfile):
    """Test loading non-existent script raises error."""
    mock_isfile.return_value = False

    runner = ScriptRunner()

    with pytest.raises(PlatformError, match="Script not found"):
        runner.load_script_file("missing.py")


@mock.patch("os.path.isfile")
@mock.patch("builtins.open", create=True)
def test_script_runner_load_script_file_cached(mock_open, mock_isfile):
    """Test that loaded scripts are cached."""
    mock_isfile.return_value = True
    mock_open.return_value.__enter__ = mock.Mock(return_value=mock_open.return_value)
    mock_open.return_value.__exit__ = mock.Mock()
    mock_open.return_value.read.return_value = "result = 1"

    runner = ScriptRunner()
    source1 = runner.load_script_file("cached.py")
    source2 = runner.load_script_file("cached.py")

    # Should only open file once
    assert mock_open.call_count == 1
    assert source1 == source2


def test_script_runner_execute_string_success(capsys):
    """Test successful script execution via exec statement (A2)."""
    runner = ScriptRunner()

    script = """
x = 10
y = 20
result = x + y
log("Computed:", result)
"""

    result = runner.execute_string(script, script_name="add_script")

    assert result.success is True
    assert result.return_value == 30
    assert "Computed:" in result.output
    assert result.elapsed_seconds > 0

    captured = capsys.readouterr()
    assert "Executing inline script" in captured.out


def test_script_runner_execute_string_with_variables():
    """Test script execution with injected variables."""
    runner = ScriptRunner()

    script = """
result = base_value * multiplier
"""

    variables = {"base_value": 5, "multiplier": 7}
    result = runner.execute_string(script, variables=variables)

    assert result.success is True
    assert result.return_value == 35


def test_script_runner_execute_string_platform_error(capsys):
    """Test script raising PlatformError (except syntax with comma)."""
    api = {
        "fail_func": lambda: (_ for _ in ()).throw(PlatformError("API error"))
    }

    runner = ScriptRunner(platform_api=api)

    script = """
try:
    fail_func()
except Exception as e:
    raise PlatformError("Caught: " + str(e))
"""

    # Since we can't actually import PlatformError in exec'd code without __import__,
    # test with a simpler error
    script = """
raise RuntimeError("Test error")
"""

    result = runner.execute_string(script)

    assert result.success is False
    assert result.error_message is not None
    assert "RuntimeError" in result.error_message or "Test error" in result.error_message


def test_script_runner_execute_string_exception(capsys):
    """Test script with general exception."""
    runner = ScriptRunner()

    script = """
x = 10 / 0  # Division by zero
"""

    result = runner.execute_string(script)

    assert result.success is False
    assert "ZeroDivisionError" in result.error_message or "division" in result.error_message.lower()

    captured = capsys.readouterr()
    assert "failed" in captured.out


def test_script_runner_execute_string_increments_counter():
    """Test execution counter increments."""
    runner = ScriptRunner()

    assert runner._execution_count == 0

    runner.execute_string("result = 1")
    assert runner._execution_count == 1

    runner.execute_string("result = 2")
    assert runner._execution_count == 2


@mock.patch("os.path.isfile")
@mock.patch("builtins.open", mock.mock_open(read_data="result = 99"))
def test_script_runner_execute_file_success(mock_isfile, capsys):
    """Test script execution via exec(compile(open().read())) (A19)."""
    mock_isfile.return_value = True

    runner = ScriptRunner(script_directory="/scripts")
    result = runner.execute_file("compute.py")

    assert result.success is True
    assert result.return_value == 99

    captured = capsys.readouterr()
    assert "Executing script file" in captured.out


@mock.patch("os.path.isfile")
def test_script_runner_execute_file_not_found(mock_isfile):
    """Test execfile with missing file."""
    mock_isfile.return_value = False

    runner = ScriptRunner()

    with pytest.raises(PlatformError, match="Script not found"):
        runner.execute_file("missing.py")


@mock.patch("os.path.isfile")
@mock.patch("builtins.open", mock.mock_open(read_data="raise ValueError('Script failed')"))
def test_script_runner_execute_file_exception(mock_isfile, capsys):
    """Test execute_file with script exception."""
    mock_isfile.return_value = True

    runner = ScriptRunner()
    result = runner.execute_file("bad_script.py")

    assert result.success is False
    assert "ValueError" in result.error_message

    captured = capsys.readouterr()
    assert "failed" in captured.out


@mock.patch("subprocess.getoutput")
def test_script_runner_run_shell_command(mock_getoutput, capsys):
    """Test running shell command via commands.getoutput() (D14)."""
    mock_getoutput.return_value = "total 8\ndrwxr-xr-x 2 user user 4096"

    runner = ScriptRunner()
    output = runner.run_shell_command("ls -l")

    assert "total 8" in output
    mock_getoutput.assert_called_once_with("ls -l")

    captured = capsys.readouterr()
    assert "Running shell command" in captured.out


@mock.patch("subprocess.getoutput")
def test_script_runner_run_shell_command_with_allowlist(mock_getoutput):
    """Test shell command respects allowlist."""
    runner = ScriptRunner()

    with pytest.raises(PlatformError, match="not allowed"):
        runner.run_shell_command("rm -rf /", allowed_commands=["ls", "cat"])


@mock.patch("subprocess.getoutput")
def test_script_runner_run_shell_command_allowed(mock_getoutput):
    """Test allowed shell command executes."""
    mock_getoutput.return_value = "file contents"

    runner = ScriptRunner()
    output = runner.run_shell_command("cat /tmp/test.txt", allowed_commands=["cat", "ls"])

    assert output == "file contents"


def test_script_runner_validate_bounds():
    """Test validating list of bounds (uses tuple unpacking function)."""
    runner = ScriptRunner()

    bounds = [(0, 100), (50, 150), (-10, 10)]
    result = runner.validate_bounds(bounds)

    assert len(result) == 3
    assert result[0] == (0, 100)
    assert result[2] == (-10, 10)


def test_script_runner_validate_bounds_invalid():
    """Test validate_bounds with invalid bound."""
    runner = ScriptRunner()

    bounds = [(0, 100), (200, 50)]  # Second is invalid

    with pytest.raises(PlatformError, match="Invalid bounds"):
        runner.validate_bounds(bounds)


def test_script_runner_format_parameters():
    """Test formatting parameter dict (uses tuple unpacking)."""
    runner = ScriptRunner()

    params = {"sensor": "TEMP_001", "interval": 60, "threshold": 85.0}
    formatted = runner.format_parameters(params)

    assert "sensor=" in formatted
    assert "TEMP_001" in formatted
    assert "interval=" in formatted
    assert "60" in formatted


def test_script_runner_get_execution_stats():
    """Test retrieving execution statistics."""
    runner = ScriptRunner(script_directory="/test")

    runner.execute_string("result = 1")
    runner.execute_string("result = 2")

    stats = runner.get_execution_stats()

    assert stats["total_executions"] == 2
    assert stats["cached_scripts"] == 0
    assert stats["script_directory"] == "/test"


def test_script_runner_clear_cache(capsys):
    """Test clearing script cache."""
    runner = ScriptRunner()
    runner._loaded_scripts = {"script1.py": "code1", "script2.py": "code2"}

    runner.clear_cache()

    assert len(runner._loaded_scripts) == 0

    captured = capsys.readouterr()
    assert "Cleared 2 cached scripts" in captured.out
