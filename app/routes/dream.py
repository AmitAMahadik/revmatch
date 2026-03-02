"""Dream routes: async job submission, job status, history."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies.auth import get_current_user_id
from app.schemas.dream import (
    DreamHistoryResponse,
    DreamJobDetailResponse,
    DreamJobResponse,
    DreamRequest,
)
from app.services.dream_job_service import DreamJobService

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_dream_job_service(request: Request) -> DreamJobService:
    db = request.app.state.db
    openai_client = request.app.state.openai_client
    azure_blob_client = getattr(request.app.state, "azure_blob_client", None)
    return DreamJobService(db=db, openai_client=openai_client, azure_blob_client=azure_blob_client)


@router.post("/dream", response_model=DreamJobResponse)
async def create_dream(
    body: DreamRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> DreamJobResponse:
    """Submit a dream job. Returns jobId and status. Poll GET /dream/{jobId} for result."""
    service = _get_dream_job_service(request)
    job_id, status, deduped = await service.submit(user_id, body)
    return DreamJobResponse(jobId=job_id, status=status, deduped=deduped)


@router.get("/dream/history", response_model=DreamHistoryResponse)
async def get_dream_history(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    cursor: str | None = None,
) -> DreamHistoryResponse:
    """Get dream job history for the current user. Paginated via cursor."""
    service = _get_dream_job_service(request)
    items, next_cursor = await service.get_history(user_id, limit=limit, cursor=cursor)
    return DreamHistoryResponse(
        items=[_serialize_dream_item(d) for d in items], nextCursor=next_cursor
    )


@router.get("/dream/{job_id}", response_model=DreamJobDetailResponse)
async def get_dream(
    job_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> DreamJobDetailResponse:
    """Get dream job status and result. 404 if not found or not owned by user."""
    service = _get_dream_job_service(request)
    job = await service.get_job(user_id, job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": {"type": "not_found", "message": "Dream job not found"}},
        )

    signed_url: str | None = None
    image_url: str | None = None

    if job.get("storageKey"):
        azure = getattr(request.app.state, "azure_blob_client", None)
        if not azure:
            raise HTTPException(
                status_code=500,
                detail={"error": {"type": "storage_error", "message": "Storage not configured"}},
            )
        signed_url = await azure.generate_signed_url(job["storageKey"], expires_minutes=60)
        image_url = signed_url
    elif (existing := job.get("imageUrl")) and existing.startswith("data:image/"):
        image_url = existing
    else:
        image_url = job.get("imageUrl")

    return DreamJobDetailResponse(
        jobId=str(job["_id"]),
        status=job["status"],
        promptUsed=job.get("promptUsed"),
        renderProfile=job.get("renderProfile"),
        meta=job.get("meta"),
        storageKey=job.get("storageKey"),
        imageUrl=image_url,
        signedUrl=signed_url,
        error=job.get("errorMessage") or job.get("error"),
    )


def _serialize_dream_item(doc: dict) -> dict:
    """Convert MongoDB doc to JSON-serializable dict."""
    out = dict(doc)
    if "_id" in out:
        out["jobId"] = str(out.pop("_id"))
    for key in ("createdAt", "updatedAt"):
        if key in out and isinstance(out[key], datetime):
            out[key] = out[key].isoformat() + "Z"
    return out
