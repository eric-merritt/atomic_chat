"""Tests for tool-related API endpoints."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create a test client with auth disabled and a mock current_user."""
    from main import app
    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = True

    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.preferences = {}

    with patch("flask_login.utils._get_user", return_value=mock_user):
        with app.test_client() as c:
            yield c


def test_workflows_returns_all_groups(client):
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "groups" in data
    names = [g["name"] for g in data["groups"]]
    assert "Filesystem" in names
    assert "Web Tools" in names
    assert "Accounting" in names


def test_workflows_includes_tool_metadata(client):
    resp = client.get("/api/workflows")
    data = resp.get_json()
    fs_group = next(g for g in data["groups"] if g["name"] == "Filesystem")
    assert "tooltip" in fs_group
    assert "tools" in fs_group
    assert len(fs_group["tools"]) > 0
    # Each tool should now be a dict with name, description, params
    tool = fs_group["tools"][0]
    assert isinstance(tool, dict)
    assert "name" in tool
    assert "description" in tool
    assert "params" in tool


def test_select_group_activates_tools(client):
    resp = client.post(
        "/api/tools/select-group",
        json={"group": "Filesystem", "active": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "selected" in data
    assert "fs_read" in data["selected"]


def test_select_group_unknown_returns_404(client):
    resp = client.post(
        "/api/tools/select-group",
        json={"group": "Nonexistent"},
        content_type="application/json",
    )
    assert resp.status_code == 404
