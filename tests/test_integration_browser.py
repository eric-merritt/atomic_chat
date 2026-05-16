"""
Integration test: full www_nav → www_login (convention path) round-trip.
Requires geckodriver. Skipped if geckodriver not found.
"""
import json
import os
import threading
import time

import pytest

GECKODRIVER = os.environ.get('GECKODRIVER_PATH', '/home/ermer/.local/bin/geckodriver')


@pytest.fixture(scope='module')
def login_flask_app():
  """Tiny Flask app serving a simple login form on port 15432."""
  flask = pytest.importorskip('flask')
  app = flask.Flask(__name__)
  app.secret_key = 'test-secret'

  @app.route('/login')
  def login_form():
    return '''<html><body>
        <form method="POST" action="/do_login">
          <input type="email" id="email" name="email" placeholder="email"/>
          <input type="password" id="password" name="password"/>
          <button type="submit">Sign in</button>
        </form></body></html>'''

  @app.route('/do_login', methods=['POST'])
  def do_login():
    if (flask.request.form.get('email') == 'user@test.com'
        and flask.request.form.get('password') == 'testpass'):
      return flask.redirect('/dashboard')
    return 'Unauthorized', 401

  @app.route('/dashboard')
  def dashboard():
    return '<html><body><h1>Welcome</h1></body></html>'

  server = threading.Thread(
    target=lambda: app.run(port=15432, use_reloader=False), daemon=True
  )
  server.start()
  time.sleep(1)
  yield 'http://localhost:15432'


@pytest.mark.skipif(
  not os.path.exists(GECKODRIVER),
  reason=f'geckodriver not found at {GECKODRIVER}'
)
def test_www_nav_then_login_convention(login_flask_app, tmp_path, monkeypatch):
  """www_nav navigates, www_login convention path fills and submits."""
  import tools.web as web_mod
  original_driver = web_mod._browser_driver
  web_mod._browser_driver = None

  import auth.credentials as cred_mod
  test_cred_file = tmp_path / '.test_creds.enc'
  monkeypatch.setattr(cred_mod, 'CRED_FILE', test_cred_file)

  cred_mod.add_credential(
    'testsite', f'{login_flask_app}/login', 'basic',
    username='user@test.com', password='testpass'
  )

  from qwen_agent.tools.base import TOOL_REGISTRY
  import tools.browser_session  # noqa — ensure registered

  nav_tool = TOOL_REGISTRY['www_nav']()
  nav_result = nav_tool.call(json.dumps({'url': f'{login_flask_app}/login'}))
  assert nav_result['status'] == 'success'
  assert 'login' in nav_result['data']['url']

  login_tool = TOOL_REGISTRY['www_login']()
  login_result = login_tool.call(json.dumps({'alias': 'testsite', 'force_convention': True}))

  assert login_result['status'] == 'success'
  assert login_result['data']['ok'] is True
  assert '/dashboard' in login_result['data']['final_url']

  if web_mod._browser_driver is not None:
    try:
      web_mod._browser_driver.quit()
    except Exception:
      pass
  web_mod._browser_driver = original_driver
