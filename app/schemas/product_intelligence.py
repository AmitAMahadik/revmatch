"""Pydantic models for Product Intelligence API (FindNext, Chat)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.recommendations import RecommendationItem


class FindNextConstraints(BaseModel):
    market: Literal["US"] = "US"
    year: int | None = None
    limit: int = Field(default=10, ge=1, le=50)


class FindNextRequest(BaseModel):
    model_config = {"extra": "forbid"}
    prompt: str
    constraints: FindNextConstraints | None = None


class FindNextResponse(BaseModel):
    items: list[RecommendationItem]
    explanation: str
    parsedQuery: dict[str, Any]


class ChatRequest(BaseModel):
    sessionId: str | None = None
    message: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    sessionId: str
    assistantMessage: str
    cards: list[dict[str, Any]] = Field(default_factory=list)
    usedTrimIds: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None

