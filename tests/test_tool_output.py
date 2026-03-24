"""Tests for tools._output module."""

import pytest
from tools._output import tool_result, retry


class TestToolResult:
    def test_success_returns_dict(self):
        result = tool_result(data={"key": "value"})
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["data"] == {"key": "value"}
        assert result["error"] == ""

    def test_error_returns_dict(self):
        result = tool_result(error="something broke")
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert result["data"] is None
        assert result["error"] == "something broke"

    def test_no_args_returns_success_with_none_data(self):
        result = tool_result()
        assert result["status"] == "success"
        assert result["data"] is None


class TestRetry:
    def test_succeeds_first_try(self):
        @retry(max_retries=3)
        def ok():
            return "done"
        assert ok() == "done"

    def test_retries_on_failure(self):
        call_count = 0
        @retry(max_retries=3, delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"
        assert flaky() == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        @retry(max_retries=2, delay=0.01)
        def always_fail():
            raise ConnectionError("fail")
        with pytest.raises(ConnectionError):
            always_fail()
