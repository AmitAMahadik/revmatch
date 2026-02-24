"""Recommendation aggregation logic (MongoDB pipelines live here; routes stay thin)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def get_recommendations(
    db: AsyncDatabase,
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

    cursor = await spec_coll.aggregate(pipeline)
    return await cursor.to_list(length=int(limit))


async def find_next(db: AsyncDatabase, parsed_query: dict) -> list[dict]:
    """Find next recommendations from specSheets using parsed query (filters, weights, limit).

    Returns a list of dicts matching RecommendationItem:
      trimId, trimName, year, market, bodyStyle, drivenWheels, hp, redline, scores
    """
    filters = parsed_query.get("filters") or {}
    weights = parsed_query.get("weights") or {}
    limit_val = int(parsed_query.get("limit", 10))
    limit_val = max(1, min(50, limit_val))

    # 1. $match on specSheets
    match: dict[str, Any] = {"market": filters.get("market", "US")}
    if filters.get("year") is not None:
        match["year"] = filters["year"]
    if filters.get("drivenWheels") is not None:
        match["drivetrain.drivenWheels"] = filters["drivenWheels"]
    if filters.get("transmission") is not None:
        match["drivetrain.transmissions"] = {
            "$elemMatch": {"type": filters["transmission"]}
        }

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
                                    {"$eq": ["$modelVersion", "v1.0.0"]},
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0, "scores": 1}},
                    {"$limit": 1},
                ],
                "as": "cs",
            }
        },
        {"$unwind": {"path": "$cs", "preserveNullAndEmptyArrays": True}},
    ]

    # 5. $match minScores (if present)
    min_scores = filters.get("minScores")
    if min_scores and isinstance(min_scores, dict):
        min_score_conditions = []
        for k, v in min_scores.items():
            if v is not None and isinstance(v, (int, float)):
                min_score_conditions.append(
                    {
                        "$gte": [
                            {
                                "$ifNull": [
                                    {"$getField": {"field": k, "input": {"$ifNull": ["$cs.scores", {}]}}},
                                    -1,
                                ]
                            },
                            float(v),
                        ]
                    }
                )
        if min_score_conditions:
            pipeline.append({"$match": {"$expr": {"$and": min_score_conditions}}})

    # 6. $addFields fitScore
    w_rh = float(weights.get("revHappiness", 0.0))
    w_sf = float(weights.get("steeringFeel", 0.0))
    w_ad = float(weights.get("acousticDrama", 0.0))
    w_dc = float(weights.get("dailyCompliance", 0.0))

    fit_score_expr = {
        "$round": [
            {
                "$add": [
                    {"$multiply": [w_rh, {"$ifNull": ["$cs.scores.revHappiness", 0]}]},
                    {"$multiply": [w_sf, {"$ifNull": ["$cs.scores.steeringFeel", 0]}]},
                    {"$multiply": [w_ad, {"$ifNull": ["$cs.scores.acousticDrama", 0]}]},
                    {"$multiply": [w_dc, {"$ifNull": ["$cs.scores.dailyCompliance", 0]}]},
                ]
            },
            2,
        ]
    }
    pipeline.append({"$addFields": {"fitScore": fit_score_expr}})

    # 7. $sort, $limit, $project
    pipeline.extend(
        [
            {"$sort": {"fitScore": -1}},
            {"$limit": limit_val},
            {
                "$project": {
                    "_id": 0,
                    "trimId": 1,
                    "trimName": "$trim.trimName",
                    "year": 1,
                    "market": 1,
                    "bodyStyle": "$trim.bodyStyle",
                    "drivenWheels": "$drivetrain.drivenWheels",
                    "hp": "$output.powerHp",
                    "redline": "$engine.redlineRpm",
                    "scores": "$cs.scores",
                }
            },
        ]
    )

    spec_coll = db["specSheets"]
    cursor = await spec_coll.aggregate(pipeline)
    return await cursor.to_list(length=limit_val)
