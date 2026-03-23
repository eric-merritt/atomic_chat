"""Test that config module exists and has required constants."""

import os


def test_config_rate_limits():
    from config import RATE_LIMITS
    assert isinstance(RATE_LIMITS, dict)
    assert "ebay" in RATE_LIMITS
    assert "amazon" in RATE_LIMITS
    assert "craigslist" in RATE_LIMITS
    assert "default" in RATE_LIMITS
    assert all(isinstance(v, (int, float)) for v in RATE_LIMITS.values())


def test_config_max_retries():
    from config import MAX_RETRIES
    assert isinstance(MAX_RETRIES, int)
    assert MAX_RETRIES >= 0


def test_config_task_extractor_model_default():
    from config import TASK_EXTRACTOR_MODEL
    assert isinstance(TASK_EXTRACTOR_MODEL, str)
    assert len(TASK_EXTRACTOR_MODEL) > 0


def test_config_tool_curator_model_default():
    from config import TOOL_CURATOR_MODEL
    assert isinstance(TOOL_CURATOR_MODEL, str)
    assert len(TOOL_CURATOR_MODEL) > 0
