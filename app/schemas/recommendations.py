"""Pydantic models for recommendations API."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class RecommendationItem(BaseModel):
    # Ignore any additional fields returned by the aggregation (e.g., specSheetId, engine, drivetrain object)
    model_config = ConfigDict(extra="ignore")

    trimId: str
    trimName: str
    year: int
    market: str
    bodyStyle: str | None = None
    drivenWheels: str | None = None
    hp: int | None = None
    redline: int | None = None
    scores: dict[str, Any] | None = None


class RecommendationsResponse(BaseModel):
    items: list[RecommendationItem]
