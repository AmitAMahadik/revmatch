"""Pydantic models for preferences catalog API."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.recommendations import RecommendationItem


class PreferencesScoreConstraints(BaseModel):
    market: Literal["US"] = "US"
    year: int | None = None
    drivenWheels: Literal["RWD", "AWD"] | None = None
    transmission: Literal["Manual", "PDK"] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class PreferencesScoreRequest(BaseModel):
    rankedAxes: list[str] = Field(default_factory=list)
    minScores: dict[str, float | None] | None = None
    constraints: PreferencesScoreConstraints = Field(
        default_factory=PreferencesScoreConstraints
    )


class ScoredRecommendationItem(RecommendationItem):
    fitScore: float


class PreferencesScoreResponse(BaseModel):
    items: list[ScoredRecommendationItem]
    weightsUsed: dict[str, float]
    filtersUsed: dict[str, Any]


class PreferenceAxis(BaseModel):
    key: str
    label: str
    shortLabel: str
    description: str
    scaleMin: int = 0
    scaleMax: int = 10
    icon: str
    defaultWeight: float
    supportsMinThreshold: bool = True


class PreferencesCatalogResponse(BaseModel):
    axes: list[PreferenceAxis]
