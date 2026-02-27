"""Tests for POST /v1/preferences/score endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.preferences_score_service import _compute_weights

# Ensure app has state.db so the route can run (TestClient may not run lifespan)
app.state.db = MagicMock()

client = TestClient(app)

MOCK_ITEMS = [
    {
        "trimId": "tr_porsche_718_cayman_982_gts_4_0",
        "trimName": "GTS 4.0",
        "bodyStyle": "Coupe",
        "year": 2024,
        "market": "US",
        "drivenWheels": "RWD",
        "hp": 394,
        "redline": 7800,
        "scores": {"revHappiness": 9.4, "acousticDrama": 9.1},
        "fitScore": 8.25,
    }
]
MOCK_WEIGHTS = {"revHappiness": 0.5, "acousticDrama": 0.5}
MOCK_FILTERS = {"market": "US", "limit": 10}


@patch("app.routes.preferences.preferences_score_service.score_preferences", new_callable=AsyncMock)
def test_score_returns_200(mock_score):
    mock_score.return_value = (MOCK_ITEMS, MOCK_WEIGHTS, MOCK_FILTERS)
    response = client.post(
        "/v1/preferences/score",
        json={"rankedAxes": ["revHappiness", "acousticDrama"]},
    )
    assert response.status_code == 200


@patch("app.routes.preferences.preferences_score_service.score_preferences", new_callable=AsyncMock)
def test_score_response_contains_items_weights_filters(mock_score):
    mock_score.return_value = (MOCK_ITEMS, MOCK_WEIGHTS, MOCK_FILTERS)
    response = client.post("/v1/preferences/score", json={})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "weightsUsed" in data
    assert "filtersUsed" in data


@patch("app.routes.preferences.preferences_score_service.score_preferences", new_callable=AsyncMock)
def test_score_items_have_fit_score(mock_score):
    mock_score.return_value = (MOCK_ITEMS, MOCK_WEIGHTS, MOCK_FILTERS)
    response = client.post("/v1/preferences/score", json={})
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert "fitScore" in item


def test_weight_normalization_empty_ranked_axes():
    weights = _compute_weights([])
    assert abs(sum(weights.values()) - 1.0) < 0.001


def test_weight_normalization_single_axis():
    weights = _compute_weights(["revHappiness"])
    assert abs(sum(weights.values()) - 1.0) < 0.001
    assert weights["revHappiness"] == 1.0


def test_weight_normalization_two_axes():
    weights = _compute_weights(["revHappiness", "acousticDrama"])
    assert abs(sum(weights.values()) - 1.0) < 0.001
    # Template [0.45, 0.25] -> sum 0.70 -> 0.45/0.70, 0.25/0.70
    expected_rh = 0.45 / 0.70
    expected_ad = 0.25 / 0.70
    assert abs(weights["revHappiness"] - expected_rh) < 0.001
    assert abs(weights["acousticDrama"] - expected_ad) < 0.001
