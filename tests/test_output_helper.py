# tests/test_output_helper.py
from tools._output import tool_result
import json

def test_success_result():
    result = tool_result(data={"foo": "bar"})
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["data"] == {"foo": "bar"}
    assert parsed["error"] == ""

def test_error_result():
    result = tool_result(error="something broke")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["data"] is None
    assert parsed["error"] == "something broke"

def test_success_with_none_data():
    result = tool_result()
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["data"] is None
