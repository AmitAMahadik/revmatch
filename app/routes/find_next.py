"""POST /v1/find-next: parse prompt, find recommendations, generate explanation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.clients.openai_client import OpenAIClient
from app.config import get_settings
from app.schemas.product_intelligence import FindNextRequest, FindNextResponse
from app.schemas.recommendations import RecommendationItem
from app.services import recommendations_service
from app.services.explanation_service import ExplanationService
from app.services.query_parser_service import QueryParserService

router = APIRouter()


@router.post("/find-next", response_model=FindNextResponse)
async def find_next(request: Request, body: FindNextRequest) -> FindNextResponse:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    constraints = body.constraints.model_dump() if body.constraints else {}

    openai_client = OpenAIClient()
    parsed_query = await QueryParserService(openai_client).parse(body.prompt, constraints)

    items = await recommendations_service.find_next(request.app.state.db, parsed_query)

    explanation = await ExplanationService(openai_client).explain(
        body.prompt, items, parsed_query
    )

    validated_items = [RecommendationItem.model_validate(i) for i in items]
    return FindNextResponse(
        items=validated_items,
        explanation=explanation,
        parsedQuery=parsed_query,
    )
