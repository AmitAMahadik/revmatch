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

from app.clients.openai_client import OpenAIClient, OpenAIClientError
from app.clients.s3_client import S3Client
from app.repositories.dream_render_repo import DreamRenderRepo
from app.schemas.dream import DreamRequest
from app.services.dream_service import DreamNotFoundError, DreamService

logger = logging.getLogger(__name__)


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


class DreamJobService:
    def __init__(
        self,
        db: AsyncDatabase,
        openai_client: OpenAIClient,
        s3_client: S3Client | None,
    ) -> None:
        self._repo = DreamRenderRepo(db)
        self._dream_service = DreamService(db=db, openai_client=openai_client)
        self._s3 = s3_client

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
        """Background: run generation, upload to S3 if configured, update doc."""
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

        storage_key: str | None = None
        image_url: str | None = None
        signed_url: str | None = None

        if response.imageUrl.startswith("data:image/png;base64,"):
            b64 = response.imageUrl.split(",", 1)[1]
            try:
                image_bytes = base64.b64decode(b64)
            except Exception as e:
                await self._repo.set_failed(job_id, user_id, f"Base64 decode failed: {e}")
                return
            if self._s3 and self._s3.is_configured():
                try:
                    storage_key = await self._s3.upload_dream_image(
                        user_id, job_id, image_bytes
                    )
                    signed_url = await self._s3.get_signed_url(storage_key)
                except Exception as e:
                    logger.exception("Dream job %s: S3 upload failed", job_id)
                    image_url = response.imageUrl
            else:
                image_url = response.imageUrl
        else:
            image_url = response.imageUrl

        await self._repo.set_completed(
            job_id,
            user_id,
            prompt_used=response.promptUsed,
            render_profile=response.renderProfile,
            meta=response.meta,
            storage_key=storage_key,
            image_url=image_url,
            signed_url=signed_url,
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
