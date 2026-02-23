"""Thin route: GET /recommendations; delegates to recommendations service."""

from fastapi import APIRouter, Query, Request

from app.schemas.recommendations import RecommendationItem, RecommendationsResponse
from app.services import recommendations_service

router = APIRouter()


@router.get("", response_model=RecommendationsResponse)
async def recommendations(
    request: Request,
    year: int | None = Query(default=None, ge=1900, le=2100),
    limit: int = Query(default=50, ge=1, le=100),
):
    db = request.app.state.db
    raw_items = await recommendations_service.get_recommendations(
        db, year=year, limit=limit
    )
    items = [RecommendationItem.model_validate(i) for i in raw_items]
    return RecommendationsResponse(items=items)
