"""Tests for dream endpoints: POST /v1/dream, GET /v1/dream/{jobId}, GET /v1/dream/history."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

# Ensure app has state.db, state.openai_client, state.s3_client so the route can run
if not hasattr(app.state, "db"):
    app.state.db = MagicMock()
if not hasattr(app.state, "openai_client"):
    app.state.openai_client = MagicMock()
if not hasattr(app.state, "s3_client"):
    app.state.s3_client = None

client = TestClient(app)

VALID_DREAM_REQUEST = {
    "trimId": "tr_718_gts40",
    "visual": {
        "colorName": "Agate Grey Metallic",
        "backgroundPreset": "canyon_road",
    },
}


@patch("app.routes.dream.DreamJobService")
def test_dream_post_returns_job_id_and_status(mock_job_service_cls):
    mock_service = MagicMock()
    mock_service.submit = AsyncMock(
        return_value=("507f1f77bcf86cd799439011", "pending", False)
    )
    mock_job_service_cls.return_value = mock_service

    response = client.post(
        "/v1/dream",
        json=VALID_DREAM_REQUEST,
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["jobId"] == "507f1f77bcf86cd799439011"
    assert data["status"] == "pending"
    assert data["deduped"] is False


@patch("app.routes.dream.DreamJobService")
def test_dream_post_dedupe_returns_existing_completed(mock_job_service_cls):
    mock_service = MagicMock()
    mock_service.submit = AsyncMock(
        return_value=("507f1f77bcf86cd799439012", "completed", True)
    )
    mock_job_service_cls.return_value = mock_service

    response = client.post(
        "/v1/dream",
        json=VALID_DREAM_REQUEST,
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["jobId"] == "507f1f77bcf86cd799439012"
    assert data["status"] == "completed"
    assert data["deduped"] is True


@patch("app.routes.dream.DreamJobService")
def test_dream_post_dedupe_returns_deduped_existing_job(mock_job_service_cls):
    """Submit returns deduped=true when existing job (pending/processing/completed) is returned."""
    mock_service = MagicMock()
    mock_service.submit = AsyncMock(
        return_value=("507f1f77bcf86cd799439013", "processing", True)
    )
    mock_job_service_cls.return_value = mock_service

    response = client.post(
        "/v1/dream",
        json=VALID_DREAM_REQUEST,
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["deduped"] is True
    assert data["status"] == "processing"


@patch("app.dependencies.auth.get_settings")
@patch("app.routes.dream.DreamJobService")
def test_dream_post_returns_401_in_prod_without_x_user_id(
    mock_job_service_cls, mock_get_settings
):
    mock_get_settings.return_value = MagicMock(env="prod")

    response = client.post("/v1/dream", json=VALID_DREAM_REQUEST)

    assert response.status_code == 401


@patch("app.dependencies.auth.get_settings")
@patch("app.routes.dream.DreamJobService")
def test_dream_post_returns_401_in_prod_with_anonymous(
    mock_job_service_cls, mock_get_settings
):
    mock_get_settings.return_value = MagicMock(env="prod")

    response = client.post(
        "/v1/dream",
        json=VALID_DREAM_REQUEST,
        headers={"X-User-Id": "anonymous"},
    )

    assert response.status_code == 401


@patch("app.dependencies.auth.get_settings")
@patch("app.routes.dream.DreamJobService")
def test_dream_get_returns_401_in_prod_without_x_user_id(
    mock_job_service_cls, mock_get_settings
):
    mock_get_settings.return_value = MagicMock(env="prod")

    response = client.get("/v1/dream/507f1f77bcf86cd799439011")

    assert response.status_code == 401


@patch("app.routes.dream.DreamJobService")
def test_dream_get_returns_404_when_not_found(mock_job_service_cls):
    mock_service = MagicMock()
    mock_service.get_job = AsyncMock(return_value=None)
    mock_job_service_cls.return_value = mock_service

    response = client.get(
        "/v1/dream/507f1f77bcf86cd799439011",
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["type"] == "not_found"


@patch("app.routes.dream.DreamJobService")
def test_user_a_cannot_fetch_user_b_job(mock_job_service_cls):
    """User A requesting job owned by user B gets 404 (not found)."""
    mock_service = MagicMock()
    mock_service.get_job = AsyncMock(return_value=None)
    mock_job_service_cls.return_value = mock_service

    response = client.get(
        "/v1/dream/507f1f77bcf86cd799439011",
        headers={"X-User-Id": "userA"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["type"] == "not_found"


@patch("app.routes.dream.DreamJobService")
def test_dream_get_returns_job_when_found(mock_job_service_cls):
    mock_service = MagicMock()
    mock_service.get_job = AsyncMock(
        return_value={
            "_id": "507f1f77bcf86cd799439011",
            "userId": "user123",
            "status": "completed",
            "promptUsed": "PROMPT",
            "renderProfile": {"stance": "sporty"},
            "meta": {"trimId": "tr_718_gts40"},
            "signedUrl": "https://s3.example.com/signed",
        }
    )
    mock_job_service_cls.return_value = mock_service

    response = client.get(
        "/v1/dream/507f1f77bcf86cd799439011",
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["jobId"] == "507f1f77bcf86cd799439011"
    assert data["status"] == "completed"
    assert data["signedUrl"] == "https://s3.example.com/signed"


@patch("app.routes.dream.DreamJobService")
def test_dream_history_returns_items(mock_job_service_cls):
    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(
        return_value=(
            [
                {
                    "_id": "507f1f77bcf86cd799439011",
                    "userId": "user123",
                    "status": "completed",
                    "createdAt": "2024-01-01T00:00:00",
                }
            ],
            None,
        )
    )
    mock_job_service_cls.return_value = mock_service

    response = client.get(
        "/v1/dream/history",
        headers={"X-User-Id": "user123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["jobId"] == "507f1f77bcf86cd799439011"
    assert data["nextCursor"] is None
