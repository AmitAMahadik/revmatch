"""User preferences repository: MongoDB async operations for user_prefs collection."""

from __future__ import annotations

from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase


class UserPrefsRepo:
    def __init__(self, db: AsyncDatabase) -> None:
        self._coll = db["user_prefs"]

    async def get_top_pick(self, user_id: str) -> dict | None:
        """Get user prefs doc with topPick and updatedAt. Returns None if no doc."""
        return await self._coll.find_one(
            {"userId": user_id},
            projection={"topPick": 1, "updatedAt": 1},
        )

    async def set_top_pick(
        self, user_id: str, item_type: str, ref_id: str
    ) -> None:
        """Upsert user prefs with topPick set."""
        now = datetime.utcnow()
        await self._coll.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "topPick": {"type": item_type, "refId": ref_id},
                    "updatedAt": now,
                }
            },
            upsert=True,
        )

    async def clear_top_pick(self, user_id: str) -> None:
        """Set topPick to null and update updatedAt."""
        now = datetime.utcnow()
        await self._coll.update_one(
            {"userId": user_id},
            {"$set": {"topPick": None, "updatedAt": now}},
            upsert=True,
        )
