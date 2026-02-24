"""Tests for POST /v1/find-next endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

# Ensure app has state.db so the route can run
if not hasattr(app.state, "db"):
    app.state.db = MagicMock()

client = TestClient(app)

# Deterministic mocks
PARSED_QUERY = {
    "filters": {"market": "US", "year": 2024},
    "weights": {
        "revHappiness": 0.45,
        "steeringFeel": 0.25,
        "acousticDrama": 0.20,
        "dailyCompliance": 0.10,
    },
    "limit": 5,
}

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
        "scores": {
            "revHappiness": 0.85,
            "dailyCompliance": 0.72,
            "steeringFeel": 0.88,
            "acousticDrama": 0.91,
        },
    }
]

EXPLANATION = "Short explanation."


@patch("app.routes.find_next.get_settings")
@patch("app.routes.find_next.ExplanationService")
@patch("app.routes.find_next.recommendations_service.find_next", new_callable=AsyncMock)
@patch("app.routes.find_next.QueryParserService")
@patch("app.routes.find_next.OpenAIClient")
def test_find_next_returns_200_with_expected_body(
    mock_openai_client,
    mock_query_parser_cls,
    mock_find_next,
    mock_explanation_cls,
    mock_get_settings,
):
    mock_get_settings.return_value.openai_api_key = "test-key"

    mock_parser_instance = MagicMock()
    mock_parser_instance.parse = AsyncMock(return_value=PARSED_QUERY)
    mock_query_parser_cls.return_value = mock_parser_instance

    mock_find_next.return_value = MOCK_ITEMS

    mock_explanation_instance = MagicMock()
    mock_explanation_instance.explain = AsyncMock(return_value=EXPLANATION)
    mock_explanation_cls.return_value = mock_explanation_instance

    response = client.post(
        "/v1/find-next",
        json={"prompt": "sporty manual cayman"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "explanation" in data
    assert "parsedQuery" in data

    expected_body = {
        "items": MOCK_ITEMS,
        "explanation": EXPLANATION,
        "parsedQuery": PARSED_QUERY,
    }
    assert data == expected_body
