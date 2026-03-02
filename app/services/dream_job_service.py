"""Async dream job service: submit jobs, run background generation, dedupe by promptHash."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

import httpx

from app.clients.openai_client import OpenAIClient, OpenAIClientError
from app.clients.azure_blob_client import AzureBlobClient
from app.repositories.dream_render_repo import DreamRenderRepo
from app.schemas.dream import DreamRequest
from app.services.dream_service import DreamNotFoundError, DreamService

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 15_000_000  # 15 MB safety cap


def _compute_prompt_hash(request: DreamRequest) -> str:
    """SHA-256 of canonical JSON of (trimId, visual, profile, size) for dedupe."""
    canonical = {
        "trimId": request.trimId,
        "visual": request.visual.model_dump(),
        "profile": request.profile.model_dump() if request.profile else None,
        "size": request.size,
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _request_snapshot(request: DreamRequest) -> dict[str, Any]:
    """Snapshot of request for storage in dream_renders."""
    return {
        "trimId": request.trimId,
        "visual": request.visual.model_dump(),
        "profile": request.profile.model_dump() if request.profile else None,
        "size": request.size,
    }


def _is_png(image_bytes: bytes) -> bool:
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    return len(image_bytes) >= 8 and image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


class DreamJobService:
    def __init__(
        self,
        db: AsyncDatabase,
        openai_client: OpenAIClient,
        azure_blob_client: AzureBlobClient | None,
    ) -> None:
        self._repo = DreamRenderRepo(db)
        self._dream_service = DreamService(db=db, openai_client=openai_client)
        self._azure = azure_blob_client

    async def submit(self, user_id: str, request: DreamRequest) -> tuple[str, str, bool]:
        """Submit a dream job. Returns (job_id, status, deduped)."""
        prompt_hash = _compute_prompt_hash(request)
        existing = await self._repo.find_by_user_and_prompt_hash_with_status_in(
            user_id, prompt_hash, ["pending", "processing", "completed"]
        )
        if existing:
            return str(existing["_id"]), existing["status"], True

        job_id = await self._repo.insert_pending(
            user_id=user_id,
            prompt_hash=prompt_hash,
            request_snapshot=_request_snapshot(request),
        )
        asyncio.create_task(self._run_job(job_id, user_id, request))
        return job_id, "pending", False

    async def _run_job(
        self, job_id: str, user_id: str, request: DreamRequest
    ) -> None:
        """Background: run generation, upload to Azure Blob, update doc with storageKey only."""
        updated = await self._repo.set_processing(job_id, user_id)
        if not updated:
            logger.warning("Dream job %s could not be set to processing", job_id)
            return

        try:
            response = await self._dream_service.generate(request)
        except DreamNotFoundError as e:
            await self._repo.set_failed(job_id, user_id, str(e))
            logger.exception("Dream job %s: trim not found", job_id)
            return
        except OpenAIClientError as e:
            await self._repo.set_failed(job_id, user_id, str(e))
            logger.exception("Dream job %s: OpenAI error", job_id)
            return
        except Exception as e:
            await self._repo.set_failed(job_id, user_id, str(e))
            logger.exception("Dream job %s: unexpected error", job_id)
            return

        # Get PNG bytes from response
        if response.imageUrl.startswith("data:image/png;base64,"):
            b64 = response.imageUrl.split(",", 1)[1]
            try:
                image_bytes = base64.b64decode(b64)
            except Exception as e:
                await self._repo.set_failed(job_id, user_id, f"Base64 decode failed: {e}")
                return
            if not _is_png(image_bytes):
                await self._repo.set_failed(job_id, user_id, "Decoded image is not a PNG")
                return
            if len(image_bytes) > MAX_IMAGE_BYTES:
                await self._repo.set_failed(
                    job_id,
                    user_id,
                    f"Image exceeds max allowed size ({MAX_IMAGE_BYTES} bytes)",
                )
                return
        elif response.imageUrl.startswith(("http://", "https://")):
            try:
                timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    resp = await client.get(response.imageUrl)
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    image_bytes = resp.content

                if not content_type.startswith("image/"):
                    await self._repo.set_failed(
                        job_id,
                        user_id,
                        f"Image fetch returned non-image content-type: {content_type or 'unknown'}",
                    )
                    return

                if not _is_png(image_bytes):
                    await self._repo.set_failed(job_id, user_id, "Fetched image is not a PNG")
                    return
                if len(image_bytes) > MAX_IMAGE_BYTES:
                    await self._repo.set_failed(
                        job_id,
                        user_id,
                        f"Image exceeds max allowed size ({MAX_IMAGE_BYTES} bytes)",
                    )
                    return
            except Exception as e:
                await self._repo.set_failed(job_id, user_id, f"Image fetch failed: {e}")
                logger.exception("Dream job %s: image fetch failed", job_id)
                return
        else:
            await self._repo.set_failed(job_id, user_id, "Unsupported image format")
            return

        if not self._azure:
            await self._repo.set_failed(job_id, user_id, "Storage not configured")
            return

        try:
            storage_key = await self._azure.upload_dream_image(
                user_id, job_id, image_bytes
            )
        except Exception as e:
            logger.exception("Dream job %s: Azure upload failed", job_id)
            await self._repo.set_failed(job_id, user_id, f"Storage upload failed: {e}")
            return

        await self._repo.set_completed(
            job_id,
            user_id,
            prompt_used=response.promptUsed,
            render_profile=response.renderProfile,
            meta=response.meta,
            storage_key=storage_key,
        )

    async def get_job(self, user_id: str, job_id: str) -> dict | None:
        job = await self._repo.find_by_id_and_user(job_id, user_id)
        if not job:
            return None
        # Stale-job detection: if processing > 10 min, mark failed
        if job.get("status") == "processing":
            started_at = job.get("startedAt")
            if isinstance(started_at, datetime):
                cutoff = datetime.utcnow() - timedelta(minutes=10)
                if started_at < cutoff:
                    await self._repo.set_stale_failed(job_id, user_id)
                    job = await self._repo.find_by_id_and_user(job_id, user_id)
        return job

    async def get_history(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        return await self._repo.find_history(user_id, limit=limit, cursor=cursor)
