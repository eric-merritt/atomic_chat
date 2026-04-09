import os
import pathlib
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock
from main import app, register_auth_bps

_bps_registered = False

@pytest.fixture
def client():
    global _bps_registered
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    if not _bps_registered:
        register_auth_bps()
        _bps_registered = True

    mock_user = MagicMock()
    mock_user.is_authenticated = True

    with patch("flask_login.utils._get_user", return_value=mock_user):
        with app.test_client() as c:
            yield c

@pytest.fixture
def home_tmp():
    """Temp dir under home so it passes the _ALLOWED_ROOTS check."""
    d = tempfile.mkdtemp(dir=os.path.expanduser("~"))
    yield pathlib.Path(d)
    shutil.rmtree(d, ignore_errors=True)

def test_read_missing_path(client):
    r = client.get('/api/files/read')
    assert r.status_code == 400

def test_read_nonexistent_file(client, home_tmp):
    r = client.get(f'/api/files/read?path={home_tmp}/nope.py')
    assert r.status_code == 404

def test_read_python_file(client, home_tmp):
    f = home_tmp / 'hello.py'
    f.write_text('x = 1\n' * 5)
    r = client.get(f'/api/files/read?path={f}')
    assert r.status_code == 200
    data = r.get_json()
    assert data['language'] == 'python'
    assert 'x = 1' in data['content']
    assert data['truncated'] is False
    assert data['lines_returned'] == 5

def test_read_truncates_at_500_lines(client, home_tmp):
    f = home_tmp / 'big.py'
    f.write_text('x = 1\n' * 600)
    r = client.get(f'/api/files/read?path={f}')
    data = r.get_json()
    assert data['truncated'] is True
    assert data['lines_returned'] == 500

def test_read_traversal_rejected(client):
    r = client.get('/api/files/read?path=/etc/../etc/passwd')
    assert r.status_code == 403

def test_read_direct_system_path_rejected(client):
    r = client.get('/api/files/read?path=/etc/passwd')
    assert r.status_code == 403

def test_serve_image(client, home_tmp):
    img = home_tmp / 'photo.png'
    img.write_bytes(b'\x89PNG\r\n\x1a\n')
    r = client.get(f'/api/files/serve?path={img}')
    assert r.status_code == 200
