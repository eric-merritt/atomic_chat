"""Tests for browser_session tools: www_nav, www_fill, www_login."""

import json
from unittest.mock import MagicMock, patch

import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration ─────────────────────────────────────────────────────────────

def test_www_nav_registered():
  import tools.browser_session  # noqa
  assert 'www_nav' in TOOL_REGISTRY


def test_www_fill_registered():
  import tools.browser_session  # noqa
  assert 'www_fill' in TOOL_REGISTRY


# ── www_nav ──────────────────────────────────────────────────────────────────

def test_www_nav_rejects_non_http():
  import tools.browser_session
  tool = TOOL_REGISTRY['www_nav']()
  result = tool.call(json.dumps({'url': 'ftp://bad.com'}))
  assert result['status'] == 'error'
  assert 'http' in result['error'].lower()


def test_www_nav_returns_url_and_title():
  import tools.browser_session
  mock_driver = MagicMock()
  mock_driver.current_url = 'https://example.com/'
  mock_driver.title = 'Example Domain'

  with patch('tools.browser_session._get_or_create_browser', return_value=mock_driver), \
       patch('tools.browser_session._handle_cf_challenge', return_value=False), \
       patch('tools.browser_session.time') as mock_time:
    mock_time.sleep = MagicMock()
    tool = TOOL_REGISTRY['www_nav']()
    result = tool.call(json.dumps({'url': 'https://example.com'}))

  assert result['status'] == 'success'
  assert result['data']['title'] == 'Example Domain'
  assert result['data']['url'] == 'https://example.com/'


# ── www_fill ─────────────────────────────────────────────────────────────────

def test_www_fill_missing_selector_returns_error():
  import tools.browser_session
  tool = TOOL_REGISTRY['www_fill']()
  result = tool.call(json.dumps({'selector': '', 'value': 'hello'}))
  assert result['status'] == 'error'


def test_www_fill_returns_selector_and_value_len():
  import tools.browser_session
  mock_driver = MagicMock()
  mock_element = MagicMock()
  mock_driver.find_element.return_value = mock_element

  with patch('tools.browser_session._get_or_create_browser', return_value=mock_driver):
    tool = TOOL_REGISTRY['www_fill']()
    result = tool.call(json.dumps({'selector': '#email', 'value': 'test@example.com'}))

  assert result['status'] == 'success'
  assert result['data']['selector'] == '#email'
  assert result['data']['value_len'] == len('test@example.com')
  mock_element.clear.assert_called_once()
  mock_element.send_keys.assert_called_once_with('test@example.com')


# ── _classify_input_field ────────────────────────────────────────────────────

def _make_el(attrs: dict):
  """Create a mock Selenium WebElement with given attributes."""
  el = MagicMock()
  el.get_attribute = lambda name: attrs.get(name)
  el.tag_name = attrs.get('tag', 'input')
  return el


def test_classify_password_field():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'password'})
  assert _classify_input_field(el) == 'password'


def test_classify_autocomplete_username():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'text', 'autocomplete': 'username'})
  assert _classify_input_field(el) == 'username'


def test_classify_autocomplete_webauthn():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'text', 'autocomplete': 'webauthn'})
  assert _classify_input_field(el) == 'username'


def test_classify_id_contains_ident():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'text', 'id': 'identifier', 'autocomplete': None})
  assert _classify_input_field(el) == 'username'


def test_classify_placeholder_email():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'text', 'placeholder': 'Enter your email', 'id': None, 'autocomplete': None})
  assert _classify_input_field(el) == 'username'


def test_classify_type_email_fallback():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'email', 'placeholder': None, 'id': None, 'autocomplete': None})
  assert _classify_input_field(el) == 'username'


def test_classify_unrelated_input_returns_none():
  from tools.browser_session import _classify_input_field
  el = _make_el({'type': 'checkbox', 'placeholder': None, 'id': None, 'autocomplete': None})
  assert _classify_input_field(el) is None


# ── www_login ────────────────────────────────────────────────────────────────

def test_www_login_registered():
  import tools.browser_session  # noqa
  assert 'www_login' in TOOL_REGISTRY


def test_www_login_missing_alias_returns_error():
  import tools.browser_session
  tool = TOOL_REGISTRY['www_login']()
  with patch('tools.browser_session.get_credential', return_value=None):
    result = tool.call(json.dumps({'alias': 'nonexistent'}))
  assert result['status'] == 'error'
  assert 'nonexistent' in result['error']


def test_www_login_no_password_field_returns_webauthn_error():
  import tools.browser_session
  mock_driver = MagicMock()
  mock_driver.current_url = 'https://example.com/login'
  mock_driver.find_elements.return_value = []

  cred = {'url': 'https://example.com/login', 'type': 'basic',
          'username': 'user', 'password': 'pass'}

  with patch('tools.browser_session.get_credential', return_value=cred), \
       patch('tools.browser_session._get_or_create_browser', return_value=mock_driver), \
       patch('tools.browser_session.time') as mock_time:
    mock_time.sleep = MagicMock()
    tool = TOOL_REGISTRY['www_login']()
    result = tool.call(json.dumps({'alias': 'example'}))

  assert result['status'] == 'error'
  assert 'webauthn' in result['error'].lower() or 'password field' in result['error'].lower()


def test_www_login_convention_path_success():
  import tools.browser_session

  mock_driver = MagicMock()
  mock_driver.current_url = 'https://example.com/dashboard'
  mock_driver.title = 'Dashboard'

  mock_username_el = _make_el({'type': 'email', 'autocomplete': None, 'id': None,
                                'class': None, 'placeholder': 'email'})
  mock_password_el = _make_el({'type': 'password'})
  mock_submit_el = MagicMock()

  mock_driver.find_elements.side_effect = lambda by, sel: (
    [mock_username_el, mock_password_el] if 'input' in sel else [mock_submit_el]
  )

  cred = {'url': 'https://example.com/login', 'type': 'basic',
          'username': 'user@example.com', 'password': 'secret'}

  with patch('tools.browser_session.get_credential', return_value=cred), \
       patch('tools.browser_session._get_or_create_browser', return_value=mock_driver), \
       patch('tools.browser_session.time') as mock_time, \
       patch('tools.browser_session._try_saved_login_flow', return_value=None):
    mock_time.sleep = MagicMock()
    tool = TOOL_REGISTRY['www_login']()
    result = tool.call(json.dumps({'alias': 'example'}))

  assert result['status'] == 'success'
  assert result['data']['mode'] == 'convention'
