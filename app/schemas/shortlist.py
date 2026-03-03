"""Pydantic models for Shortlist and Top Pick API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShortlistAddRequest(BaseModel):
    """Request body for POST /v1/shortlist."""

    model_config = {"extra": "forbid"}

    type: str = Field(description="Item type (e.g., 'dream')")
    refId: str = Field(description="Reference ID (e.g., jobId)")


class TopPickRef(BaseModel):
    """Top pick reference: type and refId."""

    model_config = {"extra": "forbid"}

    type: str
    refId: str


class ShortlistItemResponse(BaseModel):
    """Response for a shortlist item."""

    model_config = {"extra": "forbid"}

    id: str = Field(description="MongoDB ObjectId as string")
    userId: str
    type: str
    refId: str
    createdAt: datetime


class ShortlistListResponse(BaseModel):
    """Response for GET /v1/shortlist."""

    model_config = {"extra": "forbid"}

    topPick: TopPickRef | None = None
    items: list[ShortlistItemResponse] = Field(default_factory=list)
    nextCursor: str | None = None


class ShortlistDeleteResponse(BaseModel):
    """Response for DELETE /v1/shortlist/{type}/{refId}."""

    model_config = {"extra": "forbid"}

    deleted: bool
    topPickCleared: bool


class TopPickSetResponse(BaseModel):
    """Response for PUT /v1/shortlist/top-pick."""

    model_config = {"extra": "forbid"}

    topPick: TopPickRef


class TopPickClearResponse(BaseModel):
    """Response for DELETE /v1/shortlist/top-pick."""

    model_config = {"extra": "forbid"}

    topPick: None = None
