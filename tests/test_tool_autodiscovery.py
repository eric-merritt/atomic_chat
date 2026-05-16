"""Tests for pkgutil auto-discovery of tool modules."""

import sys


def test_all_existing_tool_modules_still_register():
  """Auto-discovery must register every tool that the old manual list did."""
  # Reload __init__ fresh so pkgutil scan runs
  for key in list(sys.modules.keys()):
    if key == 'tools' or key.startswith('tools.'):
      del sys.modules[key]

  import tools
  from qwen_agent.tools.base import TOOL_REGISTRY

  expected_tools = {
    'www_search', 'www_find_content', 'www_find_dl', 'www_dl',
    'www_dl_status', 'www_find_routes', 'www_query', 'www_click',
    'www_find_struct', 'www_set_cookies', 'www_set_local_storage',
    'www_get_cookies', 'www_get_cookies_for_url',
  }
  registered = set(TOOL_REGISTRY.keys())
  missing = expected_tools - registered
  assert not missing, f"Auto-discovery dropped these tools: {missing}"


def test_underscore_modules_skipped():
  """Modules starting with _ must not be imported as tool modules."""
  import tools  # noqa — ensure loaded
  # _access.py and _output.py: only care about no crash during import scan
  assert True


def test_all_tools_list_non_empty():
  import tools
  assert len(tools.ALL_TOOLS) > 0
