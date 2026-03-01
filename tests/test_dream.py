"""Tests for POST /v1/dream endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.dream import DreamResponse
from app.services.dream_service import DreamNotFoundError

# Ensure app has state.db and state.openai_client so the route can run
if not hasattr(app.state, "db"):
    app.state.db = MagicMock()
if not hasattr(app.state, "openai_client"):
    app.state.openai_client = MagicMock()

client = TestClient(app)

# Valid request body for DreamRequest
VALID_DREAM_REQUEST = {
    "trimId": "tr_718_gts40",
    "visual": {
        "colorName": "Agate Grey Metallic",
        "backgroundPreset": "canyon_road",
    },
}

# Mock response for success test
MOCK_DREAM_RESPONSE = DreamResponse(
    imageUrl="data:image/png;base64,AAA",
    promptUsed="PROMPT",
    renderProfile={
        "stance": "sporty",
        "setting": "canyon_road",
        "mood": "premium",
        "shotStyle": "clean",
        "lens": "50mm",
    },
    meta={
        "size": "1024x1024",
        "trimId": "tr_718_gts40",
        "year": 2024,
        "market": "US",
    },
)


@patch("app.routes.dream.DreamService")
def test_dream_returns_200_with_expected_body(mock_dream_service_cls):
    mock_service_instance = MagicMock()
    mock_service_instance.generate = AsyncMock(return_value=MOCK_DREAM_RESPONSE)
    mock_dream_service_cls.return_value = mock_service_instance

    response = client.post("/v1/dream", json=VALID_DREAM_REQUEST)

    assert response.status_code == 200
    data = response.json()
    assert data["imageUrl"] == "data:image/png;base64,AAA"
    assert data["promptUsed"] == "PROMPT"
    assert data["renderProfile"] == {
        "stance": "sporty",
        "setting": "canyon_road",
        "mood": "premium",
        "shotStyle": "clean",
        "lens": "50mm",
    }
    assert data["meta"] == {
        "size": "1024x1024",
        "trimId": "tr_718_gts40",
        "year": 2024,
        "market": "US",
    }


@patch("app.routes.dream.DreamService")
def test_dream_returns_404_when_not_found(mock_dream_service_cls):
    mock_service_instance = MagicMock()
    mock_service_instance.generate = AsyncMock(
        side_effect=DreamNotFoundError("No US specSheet found for trimId=tr_718_gts40")
    )
    mock_dream_service_cls.return_value = mock_service_instance

    response = client.post("/v1/dream", json=VALID_DREAM_REQUEST)

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["type"] == "not_found"
    assert "No US specSheet found for trimId=" in data["detail"]["error"]["message"]
