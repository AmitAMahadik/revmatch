"""Recommendation aggregation logic (MongoDB pipelines live here; routes stay thin)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_recommendations(
    db: AsyncIOMotorDatabase,
    *,
    year: int | None = None,
    limit: int = 50,
    market: str = "US",
    model_version: str = "v1.0.0",
) -> list[dict[str, Any]]:
    """Aggregate specSheets with trims and (optionally) characterScores.

    Returns a list of recommendation items aligned with the API schema:
      - trimId, trimName, bodyStyle, year, market
      - drivenWheels, hp, redline, scores

    Also keeps useful extra context fields (specSheetId, engine, drivetrain, output) for future UI/debug.
    """

    spec_coll = db["specSheets"]

    match: dict[str, Any] = {"market": market}
    if year is not None:
        match["year"] = year

    pipeline: list[dict[str, Any]] = [
        {"$match": match},
        {
            "$lookup": {
                "from": "trims",
                "localField": "trimId",
                "foreignField": "_id",
                "as": "trim",
            }
        },
        {"$unwind": {"path": "$trim", "preserveNullAndEmptyArrays": False}},
        {
            "$lookup": {
                "from": "characterScores",
                "let": {"t": "$trimId", "y": "$year", "m": "$market"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$trimId", "$$t"]},
                                    {"$eq": ["$year", "$$y"]},
                                    {"$eq": ["$market", "$$m"]},
                                    {"$eq": ["$modelVersion", model_version]},
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0, "scores": 1, "modelVersion": 1}},
                    {"$limit": 1},
                ],
                "as": "cs",
            }
        },
        {"$unwind": {"path": "$cs", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,

                # identifiers
                "trimId": 1,
                "year": 1,
                "market": 1,

                # trim metadata
                "trimName": "$trim.trimName",
                "bodyStyle": "$trim.bodyStyle",

                # flattened fields expected by the API schema
                "drivenWheels": "$drivetrain.drivenWheels",
                "hp": "$output.powerHp",
                "redline": "$engine.redlineRpm",
                "scores": "$cs.scores",

                # additional useful context
                "specSheetId": "$_id",
                "engine": 1,
                "drivetrain": 1,
                "output": 1,
            }
        },
        {"$limit": int(limit)},
    ]

    cursor = spec_coll.aggregate(pipeline)
    return await cursor.to_list(length=int(limit))
