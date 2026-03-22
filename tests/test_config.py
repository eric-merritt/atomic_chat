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


def test_config_prepass_model_default():
    from config import PREPASS_MODEL
    assert isinstance(PREPASS_MODEL, str)
    assert len(PREPASS_MODEL) > 0


def test_config_prepass_model_env_override(monkeypatch):
    monkeypatch.setenv("PREPASS_MODEL", "test-model:latest")
    # Re-import to pick up env var
    import importlib
    import config
    importlib.reload(config)
    assert config.PREPASS_MODEL == "test-model:latest"
    # Restore
    monkeypatch.delenv("PREPASS_MODEL")
    importlib.reload(config)
