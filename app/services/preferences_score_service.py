"""Preferences scoring: deterministic weighted aggregation over specSheets + characterScores."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.preferences import PreferencesScoreConstraints

SUPPORTED_AXES = [
    "revHappiness",
    "acousticDrama",
    "steeringFeel",
    "dailyCompliance",
    "trackReadiness",
    "depreciationStability",
]
WEIGHT_TEMPLATE = [0.45, 0.25, 0.15, 0.10, 0.03, 0.02]


def _normalize_min_scores(min_scores: dict[str, float | None] | None) -> dict[str, float | None]:
    """Normalize minScores into a complete dict over SUPPORTED_AXES.

    - Unknown keys are ignored.
    - Missing keys are set to None.
    """
    base: dict[str, float | None] = {k: None for k in SUPPORTED_AXES}
    if not min_scores or not isinstance(min_scores, dict):
        return base
    for k in SUPPORTED_AXES:
        v = min_scores.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            base[k] = float(v)
    return base


def _compute_weights(ranked_axes: list[str]) -> dict[str, float]:
    """Compute axis weights from ranked axes.

    Returns a dict for ALL SUPPORTED_AXES, summing to 1.0.
    - If ranked_axes is empty (or contains no known axes): equal weights across all axes.
    - Otherwise: apply WEIGHT_TEMPLATE to the known ranked axes (in order), renormalize,
      and assign 0.0 to unranked axes.
    """
    known = [k for k in ranked_axes if k in SUPPORTED_AXES]
    if not known:
        w = 1.0 / len(SUPPORTED_AXES)
        return {k: w for k in SUPPORTED_AXES}

    template = WEIGHT_TEMPLATE[: len(known)]
    total = float(sum(template))
    weights: dict[str, float] = {k: 0.0 for k in SUPPORTED_AXES}
    for k, w in zip(known, template):
        weights[k] = float(w) / total
    return weights


async def score_preferences(
    db: AsyncDatabase,
    *,
    ranked_axes: list[str],
    min_scores: dict[str, float | None] | None,
    constraints: PreferencesScoreConstraints,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, Any]]:
    """Score specSheets by weighted character axes. Returns (items, weights_used, filters_used)."""
    weights = _compute_weights(ranked_axes)
    min_scores_norm = _normalize_min_scores(min_scores)
    limit_val = constraints.limit

    # 1. $match on specSheets
    match: dict[str, Any] = {"market": constraints.market}
    if constraints.year is not None:
        match["year"] = constraints.year
    if constraints.drivenWheels is not None:
        match["drivetrain.drivenWheels"] = constraints.drivenWheels
    if constraints.transmission is not None:
        match["drivetrain.transmissions"] = {
            "$elemMatch": {"type": constraints.transmission}
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

    # 4. $match minScores (only keys with non-null thresholds)
    if min_scores_norm:
        min_score_conditions = []
        for k, v in min_scores_norm.items():
            if v is not None and isinstance(v, (int, float)):
                min_score_conditions.append(
                    {
                        "$gte": [
                            {
                                "$ifNull": [
                                    {
                                        "$getField": {
                                            "field": k,
                                            "input": {"$ifNull": ["$cs.scores", {}]},
                                        }
                                    },
                                    -1,
                                ]
                            },
                            float(v),
                        ]
                    }
                )
        if min_score_conditions:
            pipeline.append({"$match": {"$expr": {"$and": min_score_conditions}}})

    # 5. $addFields fitScore
    add_terms = [
        {
            "$multiply": [
                weights.get(k, 0),
                {"$ifNull": [{"$getField": {"field": k, "input": {"$ifNull": ["$cs.scores", {}]}}}, 0]},
            ]
        }
        for k in SUPPORTED_AXES
    ]
    fit_score_expr = {"$round": [{"$add": add_terms}, 2]}
    pipeline.append({"$addFields": {"fitScore": fit_score_expr}})

    # 6. $sort, $limit, $project
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
                    "fitScore": 1,
                }
            },
        ]
    )

    spec_coll = db["specSheets"]

    # PyMongo async aggregate returns an async cursor; collect results via async iteration.
    cursor = await spec_coll.aggregate(pipeline)
    items: list[dict[str, Any]] = []
    async for doc in cursor:
        items.append(doc)
        if len(items) >= limit_val:
            break

    filters_used: dict[str, Any] = {
        "market": constraints.market,
        "limit": limit_val,
        "year": constraints.year,
        "drivenWheels": constraints.drivenWheels,
        "transmission": constraints.transmission,
        "minScores": min_scores_norm,
    }

    return items, weights, filters_used
