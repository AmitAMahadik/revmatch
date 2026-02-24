"""POST /v1/find-next: parse prompt, find recommendations, generate explanation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.clients.openai_client import OpenAIClient, OpenAIClientError
from app.config import get_settings
from app.schemas.product_intelligence import FindNextRequest, FindNextResponse
from app.schemas.recommendations import RecommendationItem
from app.services import recommendations_service
from app.services.explanation_service import ExplanationService
from app.services.query_parser_service import QueryParserService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/find-next", response_model=FindNextResponse)
async def find_next(request: Request, body: FindNextRequest) -> FindNextResponse | Response:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    try:
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
    except OpenAIClientError as e:
        logger.exception("OpenAI client error")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": {"type": "openai_error", "message": str(e)}},
        )
    except Exception:
        logger.exception("Unexpected server error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"type": "internal_error", "message": "Unexpected server error"}},
        )
