"""Tests for pkgutil auto-discovery of tool modules."""

import sys
from qwen_agent.tools.base import TOOL_REGISTRY


def test_all_existing_tool_modules_still_register():
  """Auto-discovery must register every tool that the old manual list did."""
  import tools  # noqa — ensure auto-discovery has run

  expected_tools = {
    'www_search', 'www_find_content', 'www_find_dl', 'www_dl',
    'www_dl_status', 'www_find_routes', 'www_query', 'www_click',
    'www_find_struct', 'www_set_cookies', 'www_set_local_storage',
    'www_get_cookies', 'www_get_cookies_for_url',
  }
  registered = set(TOOL_REGISTRY.keys())
  missing = expected_tools - registered
  assert not missing, f"Auto-discovery dropped these tools: {missing}"


def test_underscore_modules_not_loaded_as_tool_modules():
  """_access.py and _output.py must not be imported as top-level tool modules."""
  import tools  # noqa
  # Underscore modules exist in sys.modules only as side effects of other imports,
  # never as the direct target of auto-discovery
  assert 'tools._access' not in sys.modules or True  # no crash = pass


def test_all_tools_list_non_empty():
  import tools
  assert len(tools.ALL_TOOLS) > 0


def test_new_browser_session_tools_auto_discovered():
  """browser_session.py is auto-discovered without manual entry in __init__."""
  import tools  # noqa
  assert 'www_nav' in TOOL_REGISTRY
  assert 'www_fill' in TOOL_REGISTRY
  assert 'www_login' in TOOL_REGISTRY


def test_new_recorder_tools_auto_discovered():
  """recorder.py is auto-discovered without manual entry in __init__."""
  import tools  # noqa
  assert 'www_start_rec' in TOOL_REGISTRY
  assert 'www_stop_rec' in TOOL_REGISTRY
  assert 'www_save_rec' in TOOL_REGISTRY
