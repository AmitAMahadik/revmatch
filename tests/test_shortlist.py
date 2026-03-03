"""Tests for shortlist endpoints: POST, DELETE, GET, PUT/DELETE top-pick."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

if not hasattr(app.state, "db"):
    app.state.db = MagicMock()

client = TestClient(app)

HEADERS = {"X-User-Id": "user123"}


@patch("app.routes.shortlist.UserPrefsRepo")
@patch("app.routes.shortlist.ShortlistRepo")
def test_add_item_idempotent(mock_shortlist_repo_cls, mock_prefs_repo_cls):
    """POST same type+refId twice returns same doc (idempotent)."""
    doc = {
        "_id": "507f1f77bcf86cd799439011",
        "userId": "user123",
        "type": "dream",
        "refId": "job1",
        "createdAt": datetime(2024, 1, 1, 12, 0, 0),
    }
    mock_repo = MagicMock()
    mock_repo.insert_if_not_exists = AsyncMock(return_value=doc)
    mock_shortlist_repo_cls.return_value = mock_repo

    response1 = client.post(
        "/v1/shortlist",
        json={"type": "dream", "refId": "job1"},
        headers=HEADERS,
    )
    response2 = client.post(
        "/v1/shortlist",
        json={"type": "dream", "refId": "job1"},
        headers=HEADERS,
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"] == "507f1f77bcf86cd799439011"
    assert data1["userId"] == "user123"
    assert data1["type"] == "dream"
    assert data1["refId"] == "job1"


@patch("app.routes.shortlist.UserPrefsRepo")
@patch("app.routes.shortlist.ShortlistRepo")
def test_set_top_pick_only_if_item_exists(mock_shortlist_repo_cls, mock_prefs_repo_cls):
    """PUT top-pick when ref not in shortlist returns 404."""
    mock_repo = MagicMock()
    mock_repo.find_by_user_type_ref = AsyncMock(return_value=None)
    mock_shortlist_repo_cls.return_value = mock_repo

    response = client.put(
        "/v1/shortlist/top-pick",
        json={"type": "dream", "refId": "job999"},
        headers=HEADERS,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["type"] == "not_found"


@patch("app.routes.shortlist.UserPrefsRepo")
@patch("app.routes.shortlist.ShortlistRepo")
def test_deleting_top_pick_item_clears_top_pick(
    mock_shortlist_repo_cls, mock_prefs_repo_cls
):
    """DELETE item that matches topPick clears topPick and returns topPickCleared=true."""
    mock_shortlist = MagicMock()
    mock_shortlist.delete_by_user_type_ref = AsyncMock(return_value=True)
    mock_shortlist_repo_cls.return_value = mock_shortlist

    mock_prefs = MagicMock()
    mock_prefs.get_top_pick = AsyncMock(
        return_value={"topPick": {"type": "dream", "refId": "job1"}}
    )
    mock_prefs.clear_top_pick = AsyncMock()
    mock_prefs_repo_cls.return_value = mock_prefs

    response = client.delete(
        "/v1/shortlist/dream/job1",
        headers=HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] is True
    assert data["topPickCleared"] is True


@patch("app.routes.shortlist.UserPrefsRepo")
@patch("app.routes.shortlist.ShortlistRepo")
def test_list_returns_top_pick_field(mock_shortlist_repo_cls, mock_prefs_repo_cls):
    """GET shortlist returns topPick and items."""
    mock_shortlist = MagicMock()
    mock_shortlist.list_by_user = AsyncMock(
        return_value=(
            [
                {
                    "_id": "507f1f77bcf86cd799439011",
                    "userId": "user123",
                    "type": "dream",
                    "refId": "job1",
                    "createdAt": datetime(2024, 1, 1, 12, 0, 0),
                }
            ],
            None,
        )
    )
    mock_shortlist_repo_cls.return_value = mock_shortlist

    mock_prefs = MagicMock()
    mock_prefs.get_top_pick = AsyncMock(
        return_value={"topPick": {"type": "dream", "refId": "job1"}}
    )
    mock_prefs_repo_cls.return_value = mock_prefs

    response = client.get("/v1/shortlist", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert "topPick" in data
    assert data["topPick"] == {"type": "dream", "refId": "job1"}
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["refId"] == "job1"


def test_missing_x_user_id_returns_400():
    """Any endpoint without X-User-Id returns 400 with missing_user_id."""
    response = client.post(
        "/v1/shortlist",
        json={"type": "dream", "refId": "job1"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["type"] == "missing_user_id"
