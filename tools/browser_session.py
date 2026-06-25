"""Browser session navigation tools: www_nav, www_fill, www_login."""

import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


import json
import time
from pathlib import Path

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from auth.credentials import get_credential
from tools._output import tool_result
from tools.web import _get_or_create_browser, _handle_cf_challenge, _validate_url


@register_tool('www_nav')
class BrowserNavTool(BaseTool):
  description = (
    'Navigate the headless browser session to a URL. '
    'Returns {url, title} after any redirects. '
    'Auto-handles Cloudflare challenges. '
    'Use for multi-step interactions that share browser state (e.g. www_nav → www_fill → www_click). '
    'Not needed before www_fetch or www_find_content — those manage their own browser session.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'url': {'type': 'string', 'description': 'Full URL to navigate to (must start with http:// or https://).'},
      'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after page load. Default: 3.'},
      'handle_cf': {'type': 'boolean', 'description': 'Auto-handle Cloudflare challenge. Default: true.'},
    },
    'required': ['url'],
  }

  def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    url = p.get('url', '')
    wait_seconds = max(1, min(30, p.get('wait_seconds', 3)))
    handle_cf = p.get('handle_cf', True)

    err = _validate_url(url)
    if err:
      return tool_result(error=err)

    try:
      driver = _get_or_create_browser()
      driver.get(url)
      time.sleep(wait_seconds)
      if handle_cf:
        _handle_cf_challenge(driver)
    except Exception as exc:
      return tool_result(error=f"Navigation failed: {exc}")

    return tool_result(data={'url': driver.current_url, 'title': driver.title})


@register_tool('www_fill')
class BrowserFillTool(BaseTool):
  description = (
    'Type a value into an input element on the current browser page. '
    'Returns {selector, value_len} — never echoes the value itself. '
    'Use www_nav first to ensure a page is loaded.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'selector': {'type': 'string', 'description': 'CSS selector for the input element.'},
      'value': {'type': 'string', 'description': 'Value to type into the element.'},
    },
    'required': ['selector', 'value'],
  }

  def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    selector = p.get('selector', '').strip()
    value = p.get('value', '')

    if not selector:
      return tool_result(error="selector must be a non-empty CSS selector")

    try:
      driver = _get_or_create_browser()
    except Exception as exc:
      return tool_result(error=f"No browser session: {exc}. Call www_nav first.")

    try:
      element = driver.find_element("css selector", selector)
      element.clear()
      element.send_keys(value)
    except Exception as exc:
      return tool_result(error=f"Fill failed on '{selector}': {exc}")

    return tool_result(data={'selector': selector, 'value_len': len(value)})


def _classify_input_field(el) -> str | None:
  """Classify a Selenium WebElement input as 'username', 'password', or None.

  Priority ladder — order is load-bearing.
  """
  input_type = (el.get_attribute('type') or '').lower()
  autocomplete = (el.get_attribute('autocomplete') or '').lower()
  el_id = (el.get_attribute('id') or '').lower()
  classes = (el.get_attribute('class') or '').lower()
  placeholder = (el.get_attribute('placeholder') or '').lower()

  if input_type == 'password':
    return 'password'
  if autocomplete == 'username':
    return 'username'
  if autocomplete == 'webauthn':
    return 'username'
  if input_type != 'password' and 'ident' in (el_id + ' ' + classes):
    return 'username'
  if input_type != 'password' and any(
    kw in placeholder for kw in ('email', 'username', 'user name')
  ):
    return 'username'
  if input_type in ('text', 'email'):
    return 'username'
  return None


@register_tool('www_login')
class BrowserLoginTool(BaseTool):
  description = (
    'Log into a website using a stored credential alias. '
    'Checks ~/.agent_known_logins.json for a saved flow first; '
    'falls back to convention-based heuristics (username + password field scan). '
    'Returns {ok, mode, final_url} on success or an error on failure.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'alias': {'type': 'string', 'description': 'Credential alias as stored via the credentials CLI.'},
      'force_convention': {'type': 'boolean', 'description': 'Skip saved flow and use heuristic login. Default: false.'},
    },
    'required': ['alias'],
  }

  def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    alias = p.get('alias', '').strip()
    force_convention = p.get('force_convention', False)

    cred = get_credential(alias)
    if not cred:
      return tool_result(error=f"No credential found for alias: {alias!r}")

    if not force_convention:
      saved_result = _try_saved_login_flow(alias, cred)
      if saved_result is not None:
        return saved_result

    return _convention_login(cred)


def _try_saved_login_flow(alias: str, cred: dict) -> dict | None:
  """Return tool_result if a saved flow exists for alias, else None."""
  known_logins_path = Path.home() / '.agent_known_logins.json'
  if not known_logins_path.exists():
    return None
  try:
    flows = json.loads(known_logins_path.read_text())
  except Exception:
    return None
  flow = flows.get(alias)
  if not flow:
    return None
  return _replay_login_flow(alias, flow, cred)


def _replay_login_flow(alias: str, flow: dict, cred: dict) -> dict:
  """Replay a saved login flow from ~/.agent_known_logins.json."""
  try:
    driver = _get_or_create_browser()
    driver.get(flow['url'])
    time.sleep(3)
    steps_run = 0
    for step in flow.get('steps', []):
      action = step.get('action')
      selector = step.get('selector', '')
      if action == 'type':
        value = cred.get(step.get('from_cred', ''), '')
        el = driver.find_element("css selector", selector)
        el.clear()
        el.send_keys(value)
        steps_run += 1
      elif action == 'click':
        driver.find_element("css selector", selector).click()
        time.sleep(2)
        steps_run += 1
      elif action == 'wait_for_url_contains':
        _wait_for_url_contains(driver, step.get('value', ''), timeout=10)
        steps_run += 1
    return tool_result(data={
      'ok': True, 'mode': 'saved_flow', 'steps_run': steps_run,
      'final_url': driver.current_url,
    })
  except Exception as exc:
    return tool_result(error=f"Saved flow replay failed: {exc}")


def _wait_for_url_contains(driver, substring: str, timeout: int = 10) -> None:
  for _ in range(timeout * 2):
    if substring in driver.current_url:
      return
    time.sleep(0.5)


def _convention_login(cred: dict) -> dict:
  """Heuristic login: scan for username + password fields, fill, submit."""
  login_url = cred.get('url', '')
  if not login_url:
    return tool_result(error="Credential has no url field — cannot navigate to login page")

  err = _validate_url(login_url)
  if err:
    return tool_result(error=err)

  try:
    driver = _get_or_create_browser()
    driver.get(login_url)
    time.sleep(3)

    all_inputs = driver.find_elements("css selector", "input")
    username_el = None
    password_el = None
    for input_el in all_inputs:
      kind = _classify_input_field(input_el)
      if kind == 'password' and password_el is None:
        password_el = input_el
      elif kind == 'username' and username_el is None:
        username_el = input_el

    if password_el is None:
      visible_inputs = [
        {'type': el.get_attribute('type'), 'id': el.get_attribute('id')}
        for el in all_inputs
      ]
      return tool_result(error=(
        "no password field found — possibly webauthn or multi-step login. "
        f"form_fields: {visible_inputs}"
      ))

    if username_el is not None:
      username_el.clear()
      username_el.send_keys(cred.get('username', ''))

    password_el.clear()
    password_el.send_keys(cred.get('password', ''))

    submit_el = None
    for sel in ('input[type="submit"]', 'button[type="submit"]', 'button'):
      candidates = driver.find_elements("css selector", sel)
      if candidates:
        submit_el = candidates[0]
        break

    if submit_el:
      submit_el.click()
      time.sleep(3)

    return tool_result(data={
      'ok': True, 'mode': 'convention', 'final_url': driver.current_url,
    })

  except Exception as exc:
    return tool_result(error=f"Convention login failed: {exc}")
