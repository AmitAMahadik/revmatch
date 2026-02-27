"""POST /v1/chat: orchestrate chat sessions via ChatService."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.clients.openai_client import OpenAIClient, OpenAIClientError
from app.schemas.product_intelligence import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    db: AsyncDatabase = request.app.state.db
    openai_client: OpenAIClient = request.app.state.openai_client
    service = ChatService(db, openai_client)

    try:
        result = await service.chat(body.sessionId, body.message, body.context)
        return ChatResponse(**result)
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
