"""Unit tests for QueryParserService and minScores normalization."""

import asyncio
from unittest.mock import AsyncMock

from app.services.query_parser_service import (
    MIN_SCORE_KEYS_ORDER,
    QueryParserService,
    _clamp_min_scores,
)


class TestQueryParserServiceParse:
    """Tests for QueryParserService.parse() minScores handling."""

    def test_min_scores_all_keys_none_keeps_six_key_dict(self):
        """When minScores is empty/all-None, keep 6-key dict of nulls, do not collapse to None."""
        client = AsyncMock()
        client.parse_query = AsyncMock(
            return_value={
                "filters": {
                    "market": "US",
                    "year": 2024,
                    "drivenWheels": None,
                    "transmission": None,
                    "minScores": {},
                },
                "weights": {
                    "revHappiness": 0.45,
                    "steeringFeel": 0.25,
                    "acousticDrama": 0.20,
                    "dailyCompliance": 0.10,
                },
                "limit": 10,
            }
        )
        service = QueryParserService(client)

        async def _run():
            return await service.parse("sporty cars", {})

        result = asyncio.run(_run())
        min_scores = result["filters"]["minScores"]
        assert min_scores is not None
        assert list(min_scores.keys()) == list(MIN_SCORE_KEYS_ORDER)
        assert all(v is None for v in min_scores.values())

    def test_min_scores_invalid_sets_none(self):
        """When minScores input is missing/invalid, set minScores to None."""
        client = AsyncMock()
        client.parse_query = AsyncMock(
            return_value={
                "filters": {
                    "market": "US",
                    "year": 2024,
                    "drivenWheels": None,
                    "transmission": None,
                    "minScores": "invalid",
                },
                "weights": {
                    "revHappiness": 0.45,
                    "steeringFeel": 0.25,
                    "acousticDrama": 0.20,
                    "dailyCompliance": 0.10,
                },
                "limit": 10,
            }
        )
        service = QueryParserService(client)

        async def _run():
            return await service.parse("sporty cars", {})

        result = asyncio.run(_run())
        assert result["filters"]["minScores"] is None


class TestClampMinScores:
    """Tests for _clamp_min_scores normalization."""

    def test_returns_none_when_input_missing(self):
        assert _clamp_min_scores(None) is None

    def test_returns_none_when_input_not_dict(self):
        assert _clamp_min_scores("invalid") is None
        assert _clamp_min_scores(42) is None
        assert _clamp_min_scores([]) is None

    def test_returns_all_six_keys_with_none_when_empty_dict(self):
        result = _clamp_min_scores({})
        assert result is not None
        assert list(result.keys()) == list(MIN_SCORE_KEYS_ORDER)
        assert all(v is None for v in result.values())

    def test_preserves_strict_complete_shape_with_none_for_missing(self):
        result = _clamp_min_scores({"revHappiness": 7})
        assert result is not None
        assert result["revHappiness"] == 7.0
        assert result["acousticDrama"] is None
        assert result["steeringFeel"] is None
        assert result["dailyCompliance"] is None
        assert result["trackReadiness"] is None
        assert result["depreciationStability"] is None

    def test_clamps_to_zero_ten(self):
        result = _clamp_min_scores({"revHappiness": -1, "steeringFeel": 15})
        assert result is not None
        assert result["revHappiness"] == 0.0
        assert result["steeringFeel"] == 10.0

    def test_ignores_unknown_keys(self):
        result = _clamp_min_scores({"revHappiness": 7, "unknownKey": 5})
        assert result is not None
        assert result["revHappiness"] == 7.0
        assert "unknownKey" not in result
        assert len(result) == 6

    def test_does_not_prune_none_keys(self):
        result = _clamp_min_scores({"revHappiness": 7, "acousticDrama": None})
        assert result is not None
        assert result["revHappiness"] == 7.0
        assert result["acousticDrama"] is None
        assert result["steeringFeel"] is None
        assert len(result) == 6

    def test_rescales_fractional_scores_in_zero_one_range(self):
        """Values in (0, 1] are rescaled by multiplying by 10 before clamping."""
        result = _clamp_min_scores({"revHappiness": 0.8, "steeringFeel": 0.7})
        assert result is not None
        assert result["revHappiness"] == 8.0
        assert result["steeringFeel"] == 7.0
        assert result["acousticDrama"] is None
        assert result["dailyCompliance"] is None
        assert result["trackReadiness"] is None
        assert result["depreciationStability"] is None
