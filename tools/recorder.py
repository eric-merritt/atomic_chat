"""Browser recorder tools: www_start_rec, www_stop_rec, www_save_rec."""

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result
from tools.web import _validate_url

_rec_driver = None

_KNOWN_LOGINS_PATH = Path.home() / '.agent_known_logins.json'
_USER_STRUCTURES_PATH = Path.home() / '.agent_known_structures.json'

_REC_JS = """
(function() {
  if (window.__rec_initialized) return;
  window.__rec_initialized = true;
  window.__rec_events = window.__rec_events || [];
  window.__rec_done = false;
  window.__rec_pending_label = '';

  function stableSelector(el) {
    if (el.id) return '#' + el.id;
    var testid = el.getAttribute('data-testid');
    if (testid) return '[data-testid="' + testid + '"]';
    var tag = el.tagName.toLowerCase();
    var classes = Array.from(el.classList).slice(0, 2).join('.');
    return classes ? tag + '.' + classes : tag;
  }

  function ancestry(el) {
    var chain = [];
    var cur = el.parentElement;
    while (cur && cur.tagName !== 'BODY') {
      var siblings = cur.parentElement ? cur.parentElement.children : [];
      var idx = Array.from(siblings).indexOf(cur);
      var entry = {tag: cur.tagName.toLowerCase(), i: idx, n: siblings.length};
      if (cur.id) entry.id = cur.id;
      var cls = Array.from(cur.classList).slice(0, 2);
      if (cls.length) entry.cls = cls;
      chain.unshift(entry);
      cur = cur.parentElement;
    }
    return chain;
  }

  function submitCandidates(el) {
    var form = el.closest('form');
    if (form) return {form_action: form.action || null, submit_candidates: null};
    var container = el.parentElement;
    var candidates = [];
    if (container) {
      container.querySelectorAll('button, [role="button"]').forEach(function(btn) {
        candidates.push({
          selector: stableSelector(btn),
          text_preview: btn.textContent.trim().slice(0, 60),
          onclick: btn.getAttribute('onclick')
        });
      });
      var SUBMIT_PHRASES = /sign in|submit|continue|log in|login/i;
      container.querySelectorAll('a').forEach(function(a) {
        if (a.getAttribute('onclick') || SUBMIT_PHRASES.test(a.textContent)) {
          candidates.push({
            selector: stableSelector(a),
            text_preview: a.textContent.trim().slice(0, 60),
            onclick: a.getAttribute('onclick')
          });
        }
      });
    }
    return {form_action: null, submit_candidates: candidates.length ? candidates : null};
  }

  function capture(e) {
    if (window.__rec_done) return;
    var target = e.target;
    if (!target || target === document) return;
    while (target.parentElement &&
           ['span', 'i', 'svg', 'path'].includes(target.tagName.toLowerCase())) {
      target = target.parentElement;
    }
    var isPassword = target.type === 'password';
    var sub = submitCandidates(target);
    var evt = {
      ts: Date.now() / 1000,
      kind: (e.type === 'change' || target.tagName === 'INPUT' || target.tagName === 'SELECT')
            ? 'input' : 'click',
      selector: stableSelector(target),
      tag: target.tagName.toLowerCase(),
      input_type: target.type || null,
      has_value: isPassword ? true : !!(target.value),
      text_preview: isPassword ? null : (target.textContent || target.value || '').trim().slice(0, 60),
      label: window.__rec_pending_label || null,
      form_action: sub.form_action,
      submit_candidates: sub.submit_candidates,
      ancestry: ancestry(target)
    };
    window.__rec_pending_label = '';
    window.__rec_events.push(evt);
    counter.textContent = window.__rec_events.length + ' events captured';
  }

  document.addEventListener('click', capture, true);
  document.addEventListener('change', capture, true);

  var widget = document.createElement('div');
  widget.style.cssText = [
    'position:fixed', 'top:12px', 'right:12px', 'z-index:2147483647',
    'width:250px', 'background:#111', 'color:#fff', 'border-radius:20px',
    'padding:10px 14px', 'font:13px/1.4 monospace', 'box-shadow:0 2px 12px rgba(0,0,0,.5)',
    'display:flex', 'flex-direction:column', 'gap:6px'
  ].join(';');

  var labelInput = document.createElement('input');
  labelInput.placeholder = 'Label next click...';
  labelInput.style.cssText = 'background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:4px 8px;font:inherit;width:100%;box-sizing:border-box';
  labelInput.addEventListener('change', function() {
    window.__rec_pending_label = labelInput.value;
    labelInput.value = '';
  });

  var stopBtn = document.createElement('button');
  stopBtn.textContent = '\\u25a0 Stop';
  stopBtn.style.cssText = 'background:#c00;color:#fff;border:none;border-radius:10px;padding:4px 8px;cursor:pointer;font:inherit';
  stopBtn.addEventListener('click', function() { window.__rec_done = true; });

  var counter = document.createElement('span');
  counter.textContent = '0 events captured';

  widget.appendChild(labelInput);
  widget.appendChild(stopBtn);
  widget.appendChild(counter);
  document.body.appendChild(widget);
})();
"""

_SIGNUP_FORM_ACTIONS = re.compile(r'/signup|/register|/create-account', re.I)
_SIGNUP_BUTTON_TEXT = re.compile(r'^(sign up|register|create account|get started)$', re.I)


def _create_rec_driver(url: str):
  """Create a visible (non-headless) Firefox driver for recording."""
  from selenium import webdriver
  from selenium.webdriver.firefox.options import Options
  from selenium.webdriver.firefox.service import Service

  geckodriver_path = os.environ.get('GECKODRIVER_PATH', '/home/ermer/.local/bin/geckodriver')
  profile_dir = tempfile.mkdtemp(prefix='rec_profile_')

  options = Options()
  options.set_preference('general.useragent.override',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
  options.profile = profile_dir

  service = Service(geckodriver_path)
  driver = webdriver.Firefox(service=service, options=options)
  driver.set_page_load_timeout(30)
  return driver


@register_tool('www_start_rec')
class StartRecorderTool(BaseTool):
  description = (
    'Open a visible browser window and start recording user interactions. '
    'Returns {session_id, status: "recording"} immediately. '
    'The user clicks around in the visible window. '
    'Call www_stop_rec when done to retrieve recorded events.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'url': {'type': 'string', 'description': 'URL to open in the recording browser.'},
    },
    'required': ['url'],
  }

  def call(self, params: str, **kwargs) -> dict:
    global _rec_driver
    p = json5.loads(params)
    url = p.get('url', '')

    err = _validate_url(url)
    if err:
      return tool_result(error=err)

    if _rec_driver is not None:
      return tool_result(error="A recording session is already active. Call www_stop_rec first.")

    try:
      driver = _create_rec_driver(url)
      driver.get(url)
      time.sleep(2)
      driver.execute_script(_REC_JS)
      _rec_driver = driver
    except Exception as exc:
      _rec_driver = None
      return tool_result(error=f"Failed to start recording session: {exc}")

    session_id = uuid.uuid4().hex[:8]
    return tool_result(data={'session_id': session_id, 'status': 'recording', 'url': url})


@register_tool('www_stop_rec')
class StopRecorderTool(BaseTool):
  description = (
    'End the current recording session and return captured events. '
    'Idempotent — safe to call when no session is active. '
    'Call www_save_rec afterward to persist the recorded flow.'
  )
  parameters = {'type': 'object', 'properties': {}, 'required': []}

  def call(self, params: str, **kwargs) -> dict:
    global _rec_driver
    if _rec_driver is None:
      return tool_result(data={'events': [], 'status': 'no session'})

    driver = _rec_driver
    events = []
    final_url = ''
    try:
      events = driver.execute_script('return window.__rec_events || [];') or []
      final_url = driver.current_url
    except Exception:
      pass  # driver window may have been closed by user

    try:
      driver.quit()
    except Exception:
      pass

    _rec_driver = None
    return tool_result(data={'events': events, 'final_url': final_url})


@register_tool('www_save_rec')
class SaveRecorderTool(BaseTool):
  description = (
    'Save a recorded browser session as a replayable flow. '
    'Call www_stop_rec first to get the events list. '
    'kind="login" saves to ~/.agent_known_logins.json; '
    'kind="structure" saves to ~/.agent_known_structures.json. '
    'Returns a signup warning if the form looks like a registration form — '
    're-call with confirm=true to save anyway.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'name': {'type': 'string', 'description': 'Key name for the saved flow.'},
      'kind': {'type': 'string', 'description': '"login" or "structure".'},
      'events': {'type': 'array', 'description': 'Event list from www_stop_rec.'},
      'cred_alias': {'type': 'string', 'description': 'Credential alias (required for kind=login).'},
      'confirm': {'type': 'boolean', 'description': 'Set true to save despite signup warning.'},
    },
    'required': ['name', 'kind', 'events'],
  }

  def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    name = p.get('name', '').strip()
    kind = p.get('kind', '').strip()
    events = p.get('events', [])
    cred_alias = p.get('cred_alias', '').strip()
    confirm = p.get('confirm', False)

    if not name:
      return tool_result(error="name is required")
    if kind not in ('login', 'structure'):
      return tool_result(error='kind must be "login" or "structure"')
    if kind == 'login' and not cred_alias:
      return tool_result(error="cred_alias is required for kind=login")

    if not confirm:
      warning = _detect_signup_form(events)
      if warning:
        return tool_result(data={'warning': warning})

    if kind == 'login':
      return _save_login_flow(name, events, cred_alias)
    return _save_structure_flow(name, events)


def _detect_signup_form(events: list) -> str | None:
  """Return warning string if events look like a signup form, else None."""
  for evt in events:
    form_action = evt.get('form_action') or ''
    if form_action and _SIGNUP_FORM_ACTIONS.search(form_action):
      return (f"form action '{form_action}' suggests signup, not login. "
              "Re-call with confirm=true to save anyway.")
  for evt in reversed(events):
    if evt.get('kind') == 'click':
      preview = (evt.get('text_preview') or '').strip()
      if preview and _SIGNUP_BUTTON_TEXT.match(preview):
        return (f"submit button text '{preview}' suggests signup, not login. "
                "Re-call with confirm=true to save anyway.")
      break
  return None


def _classify_event_for_login(evt: dict) -> dict | None:
  """Convert a raw recorder event into a login flow step."""
  kind = evt.get('kind')
  input_type = evt.get('input_type')
  selector = evt.get('selector', '')
  ancestry = evt.get('ancestry', [])

  if kind == 'input' and input_type == 'password':
    return {'action': 'type', 'selector': selector,
            'from_cred': 'password', 'ancestry': ancestry}
  if kind == 'input' and input_type in ('email', 'text'):
    return {'action': 'type', 'selector': selector,
            'from_cred': 'username', 'ancestry': ancestry}
  if kind == 'click':
    return {'action': 'click', 'selector': selector, 'ancestry': ancestry}
  return None


def _save_login_flow(name: str, events: list, cred_alias: str) -> dict:
  steps = [s for evt in events for s in [_classify_event_for_login(evt)] if s]
  form_action = next(
    (evt.get('form_action') for evt in events if evt.get('form_action')), None
  )
  url = form_action or ''

  existing: dict = {}
  if _KNOWN_LOGINS_PATH.exists():
    try:
      existing = json.loads(_KNOWN_LOGINS_PATH.read_text())
    except Exception:
      existing = {}

  existing[name] = {
    'url': url, 'form_action': form_action,
    'cred_alias': cred_alias, 'steps': steps,
  }
  _KNOWN_LOGINS_PATH.write_text(json.dumps(existing, indent=2))
  _KNOWN_LOGINS_PATH.chmod(0o600)

  return tool_result(data={
    'path': str(_KNOWN_LOGINS_PATH), 'name': name, 'step_count': len(steps),
  })


def _save_structure_flow(name: str, events: list) -> dict:
  existing: list = []
  if _USER_STRUCTURES_PATH.exists():
    try:
      existing = json.loads(_USER_STRUCTURES_PATH.read_text())
    except Exception:
      existing = []

  existing = [entry for entry in existing if entry.get('name') != name]
  existing.append({'name': name, 'events': events})
  _USER_STRUCTURES_PATH.write_text(json.dumps(existing, indent=2))
  _USER_STRUCTURES_PATH.chmod(0o600)

  return tool_result(data={
    'path': str(_USER_STRUCTURES_PATH), 'name': name, 'step_count': len(events),
  })
