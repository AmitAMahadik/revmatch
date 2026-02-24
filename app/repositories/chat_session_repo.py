"""Chat session repository: MongoDB async operations for chatSessions collection."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase


class ChatSessionRepo:
    def __init__(self, db: AsyncDatabase) -> None:
        self._coll = db["chatSessions"]

    async def get(self, session_id: str) -> dict | None:
        try:
            oid = ObjectId(session_id)
        except (InvalidId, TypeError):
            return None
        return await self._coll.find_one({"_id": oid})

    async def create(self, initial_context: dict | None) -> dict:
        now = datetime.utcnow()
        doc = {
            "context": initial_context or {},
            "history": [],
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self._coll.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def append_messages(self, session_id: str, messages: list[dict]) -> None:
        try:
            oid = ObjectId(session_id)
        except (InvalidId, TypeError):
            return
        now = datetime.utcnow()
        await self._coll.update_one(
            {"_id": oid},
            {
                "$set": {"updatedAt": now},
                "$push": {"history": {"$each": messages, "$slice": -20}},
            },
        )

    async def update_context(self, session_id: str, context: dict) -> None:
        try:
            oid = ObjectId(session_id)
        except (InvalidId, TypeError):
            return
        now = datetime.utcnow()
        await self._coll.update_one(
            {"_id": oid},
            {"$set": {"context": context, "updatedAt": now}},
        )

    async def set_last_results(
        self, session_id: str, parsed_query: dict, used_trim_ids: list[str]
    ) -> None:
        try:
            oid = ObjectId(session_id)
        except (InvalidId, TypeError):
            return
        now = datetime.utcnow()
        await self._coll.update_one(
            {"_id": oid},
            {
                "$set": {
                    "lastParsedQuery": parsed_query,
                    "lastUsedTrimIds": used_trim_ids,
                    "updatedAt": now,
                }
            },
        )
