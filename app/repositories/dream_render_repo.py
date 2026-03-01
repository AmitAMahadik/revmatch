"""Dream render repository: MongoDB async operations for dream_renders collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase


class DreamRenderRepo:
    def __init__(self, db: AsyncDatabase) -> None:
        self._coll = db["dream_renders"]

    async def find_by_id_and_user(self, job_id: str, user_id: str) -> dict | None:
        try:
            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return None
        return await self._coll.find_one({"_id": oid, "userId": user_id})

    async def find_completed_by_user_and_prompt_hash(
        self, user_id: str, prompt_hash: str
    ) -> dict | None:
        return await self._coll.find_one(
            {"userId": user_id, "promptHash": prompt_hash, "status": "completed"}
        )

    async def find_by_user_and_prompt_hash_with_status_in(
        self, user_id: str, prompt_hash: str, statuses: list[str]
    ) -> dict | None:
        """Find first doc matching userId, promptHash, and status in statuses."""
        return await self._coll.find_one(
            {"userId": user_id, "promptHash": prompt_hash, "status": {"$in": statuses}}
        )

    async def insert_pending(
        self,
        user_id: str,
        prompt_hash: str,
        request_snapshot: dict[str, Any],
    ) -> str:
        now = datetime.utcnow()
        doc = {
            "userId": user_id,
            "status": "pending",
            "promptHash": prompt_hash,
            "request": request_snapshot,
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self._coll.insert_one(doc)
        return str(result.inserted_id)

    async def set_processing(self, job_id: str, user_id: str) -> bool:
        try:
            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return False
        now = datetime.utcnow()
        result = await self._coll.update_one(
            {"_id": oid, "userId": user_id, "status": "pending"},
            {
                "$set": {
                    "status": "processing",
                    "startedAt": now,
                    "attempts": 1,
                    "updatedAt": now,
                }
            },
        )
        return result.modified_count > 0

    async def set_completed(
        self,
        job_id: str,
        user_id: str,
        *,
        prompt_used: str,
        render_profile: dict[str, str],
        meta: dict[str, Any] | None,
        storage_key: str | None = None,
        image_url: str | None = None,
        signed_url: str | None = None,
    ) -> bool:
        try:
            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return False
        now = datetime.utcnow()
        update: dict[str, Any] = {
            "status": "completed",
            "promptUsed": prompt_used,
            "renderProfile": render_profile,
            "meta": meta or {},
            "finishedAt": now,
            "updatedAt": now,
        }
        if storage_key is not None:
            update["storageKey"] = storage_key
        if image_url is not None:
            update["imageUrl"] = image_url
        if signed_url is not None:
            update["signedUrl"] = signed_url
        result = await self._coll.update_one(
            {"_id": oid, "userId": user_id},
            {"$set": update},
        )
        return result.modified_count > 0

    async def set_failed(self, job_id: str, user_id: str, error: str) -> bool:
        try:
            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return False
        now = datetime.utcnow()
        result = await self._coll.update_one(
            {"_id": oid, "userId": user_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "errorMessage": error,
                    "finishedAt": now,
                    "updatedAt": now,
                }
            },
        )
        return result.modified_count > 0

    async def set_stale_failed(self, job_id: str, user_id: str) -> bool:
        """Mark a stale (running > 10 min) job as failed."""
        try:
            oid = ObjectId(job_id)
        except (InvalidId, TypeError):
            return False
        now = datetime.utcnow()
        result = await self._coll.update_one(
            {"_id": oid, "userId": user_id, "status": "processing"},
            {
                "$set": {
                    "status": "failed",
                    "error": "stale job timeout",
                    "errorMessage": "stale job timeout",
                    "finishedAt": now,
                    "updatedAt": now,
                }
            },
        )
        return result.modified_count > 0

    async def find_history(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        query: dict[str, Any] = {"userId": user_id}
        if cursor:
            try:
                cursor_oid = ObjectId(cursor)
                query["_id"] = {"$lt": cursor_oid}
            except (InvalidId, TypeError):
                pass
        cursor_obj = self._coll.find(query).sort("_id", -1).limit(limit + 1)
        docs = await cursor_obj.to_list(length=limit + 1)
        items = docs[:limit]
        next_cursor = str(docs[limit]["_id"]) if len(docs) > limit else None
        return items, next_cursor
