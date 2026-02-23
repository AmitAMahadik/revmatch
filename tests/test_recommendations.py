"""Basic recommendations endpoint test; mocks service to avoid DB."""

from unittest.mock import MagicMock, AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

# Ensure app has state.db so the route can run (TestClient may not run lifespan for every request)
if not hasattr(app.state, "db"):
    app.state.db = MagicMock()

client = TestClient(app)

MOCK_ITEMS = [
    {
        "trimId": "tr_porsche_718_cayman_982_gts_4_0",
        "trimName": "GTS 4.0",
        "bodyStyle": "Coupe",
        "year": 2024,
        "market": "US",
        "specSheetId": "sp_tr_porsche_718_cayman_982_gts_4_0_2024_us",
    }
]


@patch("app.routes.recommendations.recommendations_service.get_recommendations", new_callable=AsyncMock)
def test_recommendations_returns_items(mock_get):
    mock_get.return_value = MOCK_ITEMS
    response = client.get("/recommendations?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == MOCK_ITEMS
    mock_get.assert_called_once()


@patch("app.routes.recommendations.recommendations_service.get_recommendations", new_callable=AsyncMock)
def test_recommendations_accepts_year_and_limit(mock_get):
    mock_get.return_value = []
    response = client.get("/recommendations?year=2024&limit=5")
    assert response.status_code == 200
    mock_get.assert_called_once()
    call_kw = mock_get.call_args[1]
    assert call_kw.get("year") == 2024
    assert call_kw.get("limit") == 5
