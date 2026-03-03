"""Shortlist repository: MongoDB async operations for shortlist_items collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase


class ShortlistRepo:
    def __init__(self, db: AsyncDatabase) -> None:
        self._coll = db["shortlist_items"]

    async def find_by_user_type_ref(
        self, user_id: str, item_type: str, ref_id: str
    ) -> dict | None:
        """Find shortlist item by userId, type, and refId."""
        return await self._coll.find_one(
            {"userId": user_id, "type": item_type, "refId": ref_id}
        )

    async def insert_if_not_exists(
        self, user_id: str, item_type: str, ref_id: str
    ) -> dict:
        """Insert item if not exists; return existing doc if duplicate (idempotent)."""
        existing = await self.find_by_user_type_ref(user_id, item_type, ref_id)
        if existing:
            return existing
        now = datetime.utcnow()
        doc = {
            "userId": user_id,
            "type": item_type,
            "refId": ref_id,
            "createdAt": now,
        }
        result = await self._coll.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def delete_by_user_type_ref(
        self, user_id: str, item_type: str, ref_id: str
    ) -> bool:
        """Delete item if present. Returns True if deleted."""
        result = await self._coll.delete_one(
            {"userId": user_id, "type": item_type, "refId": ref_id}
        )
        return result.deleted_count > 0

    async def list_by_user(
        self,
        user_id: str,
        item_type: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """List items for user, optionally filtered by type. Paginated by _id desc."""
        query: dict[str, Any] = {"userId": user_id}
        if item_type:
            query["type"] = item_type
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
