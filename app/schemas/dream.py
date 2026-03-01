"""Pydantic models for Dream Porsche image generation API.

This contract supports the "Option B" flow:
- Client sends a selected trimId + visual preferences + optional preference profile.
- Backend deterministically derives a renderProfile and builds the final image prompt.
- Backend returns the generated image plus the promptUsed and renderProfile.

Note: imageUrl may be a remote URL or a data URL (data:image/png;base64,...).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DreamVisual(BaseModel):
    """User-selected visual preferences for the dream render."""

    model_config = {"extra": "forbid"}

    colorName: str = Field(description="Exterior paint color name (e.g., 'Agate Grey Metallic')")
    backgroundPreset: str = Field(
        description="Visual background preset key (e.g., 'canyon_road', 'coastal_cliffs', 'city_night')"
    )
    angle: str = Field(default="front_3q", description="Camera angle preset (e.g., front_3q, side, rear_3q)")
    timeOfDay: str = Field(default="golden_hour", description="Lighting/time preset (e.g., golden_hour, night, overcast)")


class DreamProfile(BaseModel):
    """Optional preference profile used to influence the render style (Option B)."""

    model_config = {"extra": "forbid"}

    rankedAxes: list[str] = Field(
        default_factory=list,
        description="Preference axes ordered from highest to lowest priority (camelCase keys from /v1/preferences/catalog)",
    )
    minScores: dict[str, float | None] | None = Field(
        default=None,
        description="Optional minimum thresholds for preference axes; keys should be camelCase axis keys.",
    )


class DreamRequest(BaseModel):
    """Request to generate a dream image for a specific trim."""

    model_config = {"extra": "forbid"}

    trimId: str = Field(description="Trim identifier (e.g., tr_718_gts40)")
    visual: DreamVisual
    profile: DreamProfile | None = Field(default=None, description="Optional preference profile for Option B styling")
    size: str = Field(default="1024x1024", description="Image dimensions (e.g., 1024x1024)")


class DreamResponse(BaseModel):
    """Response containing the generated image and metadata."""

    model_config = {"extra": "forbid"}

    imageUrl: str = Field(description="URL or base64 data URL of the generated image")
    promptUsed: str = Field(description="Final prompt sent to the image model")
    renderProfile: dict[str, str] = Field(
        description="Deterministic render profile derived from rankedAxes (stance/setting/mood/shotStyle/lens)"
    )
    meta: dict[str, Any] | None = Field(default=None, description="Optional metadata (e.g., model, size)")


class DreamJobResponse(BaseModel):
    """Response from POST /v1/dream (async job submission)."""

    model_config = {"extra": "forbid"}

    jobId: str = Field(description="Job identifier for polling")
    status: str = Field(description="Job status: pending, processing, or completed")
    deduped: bool = Field(
        default=False,
        description="True if an existing job was returned instead of creating a new one",
    )


class DreamJobDetailResponse(BaseModel):
    """Response from GET /v1/dream/{jobId}."""

    model_config = {"extra": "forbid"}

    jobId: str
    status: str
    promptUsed: str | None = None
    renderProfile: dict[str, str] | None = None
    meta: dict[str, Any] | None = None
    imageUrl: str | None = None
    signedUrl: str | None = None
    error: str | None = None


class DreamHistoryResponse(BaseModel):
    """Response from GET /v1/dream/history."""

    model_config = {"extra": "forbid"}

    items: list[dict[str, Any]] = Field(default_factory=list)
    nextCursor: str | None = None
