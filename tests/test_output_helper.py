# tests/test_output_helper.py
from tools._output import tool_result
import json

def test_success_result():
    result = tool_result(data={"foo": "bar"})
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert result["data"] == {"foo": "bar"}
    assert result["error"] == ""

def test_error_result():
    result = tool_result(error="something broke")
    assert isinstance(result, dict)
    assert result["status"] == "error"
    assert result["data"] is None
    assert result["error"] == "something broke"

def test_success_with_none_data():
    result = tool_result()
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert result["data"] is None
