"""Test that config module exists and has required constants."""


def test_config_ports():
    from config import AGENT_PORTS
    assert isinstance(AGENT_PORTS, dict)
    assert "filesystem" in AGENT_PORTS
    assert "codesearch" in AGENT_PORTS
    assert "web" in AGENT_PORTS
    assert "marketplace" in AGENT_PORTS
    assert "dispatcher" in AGENT_PORTS


def test_config_models():
    from config import AGENT_MODELS, AGENT_PORTS
    assert isinstance(AGENT_MODELS, dict)
    assert set(AGENT_MODELS.keys()) == set(AGENT_PORTS.keys())


def test_config_rate_limits():
    from config import RATE_LIMITS
    assert isinstance(RATE_LIMITS, dict)
    assert "ebay" in RATE_LIMITS
    assert "amazon" in RATE_LIMITS
    assert "craigslist" in RATE_LIMITS
    assert "default" in RATE_LIMITS
    assert all(isinstance(v, (int, float)) for v in RATE_LIMITS.values())
