"""POST /v1/dream: generate Dream Porsche images via DreamService."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.clients.openai_client import OpenAIClient, OpenAIClientError
from app.schemas.dream import DreamRequest, DreamResponse
from app.services.dream_service import DreamNotFoundError, DreamService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/dream", response_model=DreamResponse)
async def dream(request: Request, body: DreamRequest) -> DreamResponse:
    db = request.app.state.db
    openai_client = request.app.state.openai_client
    service = DreamService(db=db, openai_client=openai_client)

    try:
        return await service.generate(body)
    except DreamNotFoundError as e:
        logger.exception("Dream not found")
        raise HTTPException(
            status_code=404,
            detail={"error": {"type": "not_found", "message": str(e)}},
        )
    except OpenAIClientError as e:
        logger.exception("OpenAI client error")
        raise HTTPException(
            status_code=502,
            detail={"error": {"type": "openai_error", "message": str(e)}},
        )
    except Exception:
        logger.exception("Unexpected server error")
        raise HTTPException(
            status_code=500,
            detail={"error": {"type": "internal_error", "message": "Unexpected server error"}},
        )
