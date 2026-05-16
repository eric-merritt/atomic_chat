"""Tests for recorder tools: www_start_rec, www_stop_rec, www_save_rec."""

import json
from unittest.mock import MagicMock, patch

import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration ─────────────────────────────────────────────────────────────

def test_www_start_rec_registered():
  import tools.recorder  # noqa
  assert 'www_start_rec' in TOOL_REGISTRY


def test_www_stop_rec_registered():
  import tools.recorder  # noqa
  assert 'www_stop_rec' in TOOL_REGISTRY


def test_www_save_rec_registered():
  import tools.recorder  # noqa
  assert 'www_save_rec' in TOOL_REGISTRY


# ── www_stop_rec ─────────────────────────────────────────────────────────────

def test_www_stop_rec_idempotent_when_no_session():
  import tools.recorder as rec_mod
  rec_mod._rec_driver = None
  tool = TOOL_REGISTRY['www_stop_rec']()
  result = tool.call('{}')
  assert result['status'] == 'success'
  assert result['data']['status'] == 'no session'
  assert result['data']['events'] == []


def test_www_stop_rec_drains_events_and_quits():
  import tools.recorder as rec_mod
  mock_driver = MagicMock()
  sample_events = [
    {'ts': 1.0, 'kind': 'click', 'selector': 'button.login',
     'tag': 'button', 'input_type': None, 'has_value': False,
     'text_preview': 'Sign in', 'label': None,
     'form_action': '/api/login', 'submit_candidates': None, 'ancestry': []}
  ]
  mock_driver.execute_script.return_value = sample_events
  mock_driver.current_url = 'https://example.com/dashboard'
  rec_mod._rec_driver = mock_driver

  tool = TOOL_REGISTRY['www_stop_rec']()
  result = tool.call('{}')

  assert result['status'] == 'success'
  assert len(result['data']['events']) == 1
  assert result['data']['events'][0]['kind'] == 'click'
  mock_driver.quit.assert_called_once()
  assert rec_mod._rec_driver is None


# ── www_start_rec ────────────────────────────────────────────────────────────

def test_www_start_rec_rejects_non_http():
  import tools.recorder
  tool = TOOL_REGISTRY['www_start_rec']()
  result = tool.call(json.dumps({'url': 'ftp://bad.com'}))
  assert result['status'] == 'error'


def test_www_start_rec_returns_session_id():
  import tools.recorder as rec_mod
  rec_mod._rec_driver = None  # ensure clean state

  mock_driver = MagicMock()
  mock_driver.current_url = 'https://example.com'

  with patch('tools.recorder._create_rec_driver', return_value=mock_driver), \
       patch('tools.recorder.time') as mock_time:
    mock_time.sleep = MagicMock()
    tool = TOOL_REGISTRY['www_start_rec']()
    result = tool.call(json.dumps({'url': 'https://example.com'}))

  assert result['status'] == 'success'
  assert 'session_id' in result['data']
  assert result['data']['status'] == 'recording'

  # cleanup
  rec_mod._rec_driver = None


def test_www_start_rec_rejects_duplicate_session():
  import tools.recorder as rec_mod
  rec_mod._rec_driver = MagicMock()  # simulate active session

  tool = TOOL_REGISTRY['www_start_rec']()
  result = tool.call(json.dumps({'url': 'https://example.com'}))
  assert result['status'] == 'error'
  assert 'already active' in result['error']

  rec_mod._rec_driver = None  # cleanup


# ── www_save_rec ─────────────────────────────────────────────────────────────

def test_www_save_rec_signup_warning_without_confirm():
  import tools.recorder
  events = [
    {'ts': 1.0, 'kind': 'input', 'selector': '#email', 'tag': 'input',
     'input_type': 'email', 'has_value': True, 'text_preview': None,
     'label': 'email', 'form_action': '/signup', 'submit_candidates': None, 'ancestry': []},
    {'ts': 2.0, 'kind': 'click', 'selector': 'button.submit', 'tag': 'button',
     'input_type': None, 'has_value': False, 'text_preview': 'Sign up',
     'label': None, 'form_action': '/signup', 'submit_candidates': None, 'ancestry': []},
  ]
  tool = TOOL_REGISTRY['www_save_rec']()
  result = tool.call(json.dumps({
    'name': 'mysite', 'kind': 'login', 'events': events,
    'cred_alias': 'mysite', 'confirm': False
  }))
  assert result['status'] == 'success'
  assert 'warning' in result['data']
  assert 'confirm=true' in result['data']['warning']


def test_www_save_rec_login_flow_persisted(tmp_path, monkeypatch):
  import tools.recorder as rec_mod
  logins_path = tmp_path / '.agent_known_logins.json'
  monkeypatch.setattr(rec_mod, '_KNOWN_LOGINS_PATH', logins_path)

  events = [
    {'ts': 1.0, 'kind': 'input', 'selector': '#email', 'tag': 'input',
     'input_type': 'email', 'has_value': True, 'text_preview': None,
     'label': 'email field', 'form_action': '/api/login', 'submit_candidates': None,
     'ancestry': [{'tag': 'form', 'i': 0, 'n': 1}]},
    {'ts': 2.0, 'kind': 'input', 'selector': '#password', 'tag': 'input',
     'input_type': 'password', 'has_value': True, 'text_preview': None,
     'label': None, 'form_action': '/api/login', 'submit_candidates': None,
     'ancestry': [{'tag': 'form', 'i': 0, 'n': 1}]},
    {'ts': 3.0, 'kind': 'click', 'selector': 'button[type=submit]', 'tag': 'button',
     'input_type': None, 'has_value': False, 'text_preview': 'Sign in',
     'label': None, 'form_action': '/api/login', 'submit_candidates': None,
     'ancestry': [{'tag': 'form', 'i': 0, 'n': 1}]},
  ]

  tool = TOOL_REGISTRY['www_save_rec']()
  result = tool.call(json.dumps({
    'name': 'example', 'kind': 'login', 'events': events,
    'cred_alias': 'example', 'confirm': False
  }))

  assert result['status'] == 'success'
  assert result['data']['step_count'] == 3
  saved = json.loads(logins_path.read_text())
  assert 'example' in saved
  assert saved['example']['cred_alias'] == 'example'
  assert len(saved['example']['steps']) == 3
