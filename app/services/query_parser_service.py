"""Query parser service: wraps OpenAIClient.parse_query and validates/normalizes the result."""

from __future__ import annotations

from typing import Any, Final

from app.clients.openai_client import OpenAIClient


class QueryParserError(Exception):
    """Raised when parsed query has invalid shape or fails validation."""


DEFAULT_WEIGHTS = {
    "revHappiness": 0.45,
    "steeringFeel": 0.25,
    "acousticDrama": 0.20,
    "dailyCompliance": 0.10,
}

REQUIRED_WEIGHT_KEYS = ("revHappiness", "steeringFeel", "acousticDrama", "dailyCompliance")

ALLOWED_FILTER_KEYS: Final[set[str]] = {"market", "year", "drivenWheels", "transmission", "minScores"}
ALLOWED_MIN_SCORE_KEYS: Final[set[str]] = {
    "revHappiness",
    "acousticDrama",
    "steeringFeel",
    "dailyCompliance",
    "trackReadiness",
    "depreciationStability",
}
ALLOWED_DRIVEN_WHEELS: Final[set[str]] = {"RWD", "AWD"}
ALLOWED_TRANSMISSIONS: Final[set[str]] = {"Manual", "PDK"}
YEAR_MIN: Final[int] = 1990
YEAR_MAX: Final[int] = 2030


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


MIN_SCORE_KEYS_ORDER: Final[tuple[str, ...]] = (
    "revHappiness",
    "acousticDrama",
    "steeringFeel",
    "dailyCompliance",
    "trackReadiness",
    "depreciationStability",
)


def _clamp_min_scores(min_scores: dict[str, Any] | None) -> dict[str, float | None] | None:
    """Normalize minScores to a strict + complete shape.

    - Returns None if input is missing or not a dict
    - Otherwise returns a dict with all 6 keys; use None for missing/unspecified
    - Clamps numeric thresholds to [0, 10]
    - Does not prune None keys
    """
    if min_scores is None or not isinstance(min_scores, dict):
        return None

    result: dict[str, float | None] = {}
    for k in MIN_SCORE_KEYS_ORDER:
        v = min_scores.get(k)
        if v is None:
            result[k] = None
        elif isinstance(v, (int, float)):
            fv = float(v)
            if 0 < fv <= 1:
                fv = fv * 10
            result[k] = _clamp(fv, 0.0, 10.0)
        else:
            result[k] = None

    return result


def _normalize_weights(weights: dict[str, float] | None) -> dict[str, float]:
    """Ensure all 4 weight keys exist and sum to 1.0. Use defaults if sum is 0."""
    out: dict[str, float] = dict(DEFAULT_WEIGHTS)
    if not weights or not isinstance(weights, dict):
        return out

    for key in REQUIRED_WEIGHT_KEYS:
        val = weights.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            out[key] = float(val)
        # else keep default

    total = sum(out.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)

    return {k: v / total for k, v in out.items()}


class QueryParserService:
    """Wraps OpenAIClient.parse_query and validates/normalizes the result."""

    def __init__(self, openai_client: OpenAIClient) -> None:
        self._client = openai_client

    async def parse(self, prompt: str, constraints: dict | None) -> dict[str, Any]:
        """Parse user prompt into a validated, normalized query dict.

        Returns dict with shape: {filters, weights, limit}.

        - Enforces filters.market = "US"
        - Merges constraints (year, limit) as defaults when parsed values are missing
        - Clamps minScores values to [0, 10]
        - Ensures weights has all 4 keys and sums to 1.0
        - Clamps limit to [1, 50]

        Raises:
            QueryParserError: If parsed result has invalid shape.
        """
        constraints = constraints or {}
        parsed = await self._client.parse_query(prompt, constraints)

        if not isinstance(parsed, dict):
            raise QueryParserError("Parsed query is not a dict")

        filters = parsed.get("filters")
        weights = parsed.get("weights")
        limit = parsed.get("limit")

        if filters is None or not isinstance(filters, dict):
            raise QueryParserError("Parsed query missing or invalid 'filters' (must be a dict)")

        # Enforce filters.market = "US"
        filters = dict(filters)

        # Keep only allowed filter keys (defense-in-depth)
        filters = {k: v for k, v in filters.items() if k in ALLOWED_FILTER_KEYS}

        filters["market"] = "US"

        # Merge constraints: year
        if filters.get("year") is None and constraints.get("year") is not None:
            filters["year"] = constraints["year"]

        # Sanitize year
        year = filters.get("year")
        if year is not None:
            if isinstance(year, bool) or not isinstance(year, (int, float)):
                filters["year"] = None
            else:
                year_i = int(year)
                if year_i < YEAR_MIN or year_i > YEAR_MAX:
                    filters["year"] = None
                else:
                    filters["year"] = year_i

        # Sanitize drivenWheels
        dw = filters.get("drivenWheels")
        if dw is not None and dw not in ALLOWED_DRIVEN_WHEELS:
            filters["drivenWheels"] = None

        # Sanitize transmission
        tx = filters.get("transmission")
        if tx is not None and tx not in ALLOWED_TRANSMISSIONS:
            filters["transmission"] = None

        # Normalize minScores to strict + complete shape (all 6 keys, None for unspecified)
        if "minScores" in filters:
            normalized = _clamp_min_scores(filters.get("minScores"))
            if normalized is None:
                filters["minScores"] = None
            else:
                filters["minScores"] = normalized

        # Normalize weights
        weights = _normalize_weights(weights)

        # Merge constraints: limit
        if limit is None:
            limit = constraints.get("limit", 10)
        if not isinstance(limit, (int, float)):
            limit = 10
        limit = int(limit)
        limit = max(1, min(50, limit))

        return {
            "filters": filters,
            "weights": weights,
            "limit": limit,
        }
