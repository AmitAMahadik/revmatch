
"""Dream Porsche image generation service.

Option B contract:
- Client sends: trimId + visual prefs + optional preference profile.
- Backend deterministically derives a renderProfile and builds the final image prompt.
- Backend grounds the prompt in MongoDB (trims + specSheets) and calls OpenAI Images API.

Note: imageUrl may be a remote URL or a data URL (data:image/png;base64,...).
"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.clients.openai_client import OpenAIClient
from app.schemas.dream import DreamRequest, DreamResponse


class DreamNotFoundError(Exception):
    """Raised when the requested trim/spec data cannot be found."""


DEFAULT_RENDER_PROFILE: dict[str, str] = {
    "stance": "sporty",
    "setting": "canyon_road",
    "mood": "premium",
    "shotStyle": "clean",
    "lens": "50mm",
}


def _derive_render_profile_top2(ranked_axes: list[str]) -> dict[str, str]:
    """Derive a deterministic render profile from the top-2 ranked axes.

    This intentionally avoids LLM calls so rendering is reproducible.

    Rules (top-2 axes):
    - stance: aggressive if trackReadiness is top-2
    - setting: tunnel if acousticDrama is top-2; track if trackReadiness is top-2; else canyon
    - mood: refined if dailyCompliance is top-2; else cinematic
    - shotStyle: rolling/action if revHappiness is top-2; else clean/static
    - lens: 35mm if steeringFeel is top-2; else 50mm
    """

    if not ranked_axes:
        return dict(DEFAULT_RENDER_PROFILE)

    top2 = set(ranked_axes[:2])

    stance = "aggressive" if "trackReadiness" in top2 else "sporty"

    if "acousticDrama" in top2:
        setting = "tunnel"
    elif "trackReadiness" in top2:
        setting = "race_track"
    else:
        setting = "canyon_road"

    mood = "refined" if "dailyCompliance" in top2 else "cinematic"

    shot_style = "rolling_action" if "revHappiness" in top2 else "clean_static"

    lens = "35mm" if "steeringFeel" in top2 else "50mm"

    return {
        "stance": stance,
        "setting": setting,
        "mood": mood,
        "shotStyle": shot_style,
        "lens": lens,
    }


def _pretty_preset(value: str) -> str:
    return value.replace("_", " ").strip()


async def get_trim_snapshot(db: AsyncDatabase, trim_id: str) -> dict[str, Any]:
    """Fetch a grounded snapshot for prompt building.

    Strategy:
    - Find the latest US specSheet for the trim (max year)
    - Join trims to obtain trimName and bodyStyle
    - Optionally join characterScores for the same (trimId, year, market, modelVersion)
    """

    spec_coll = db["specSheets"]

    pipeline: list[dict[str, Any]] = [
        {"$match": {"trimId": trim_id, "market": "US"}},
        {"$sort": {"year": -1}},
        {"$limit": 1},
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
                "let": {"trimId": "$trimId", "year": "$year", "market": "$market"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$trimId", "$$trimId"]},
                                    {"$eq": ["$year", "$$year"]},
                                    {"$eq": ["$market", "$$market"]},
                                    {"$eq": ["$modelVersion", "v1.0.0"]},
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0, "scores": 1}},
                ],
                "as": "cs",
            }
        },
        {"$unwind": {"path": "$cs", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "trimId": 1,
                "year": 1,
                "market": 1,
                "trimName": "$trim.trimName",
                "bodyStyle": "$trim.bodyStyle",
                "drivenWheels": "$drivetrain.drivenWheels",
                "hp": "$output.powerHp",
                "redline": "$engine.redlineRpm",
                "scores": "$cs.scores",
            }
        },
    ]

    cursor = await spec_coll.aggregate(pipeline)
    docs = await cursor.to_list(length=1)
    if not docs:
        # Could be missing trim or missing US specSheets for that trim
        raise DreamNotFoundError(f"No US specSheet found for trimId={trim_id}")

    snap = docs[0]
    # Defensive: ensure trimName exists (lookup should enforce it)
    if not snap.get("trimName"):
        raise DreamNotFoundError(f"Trim not found for trimId={trim_id}")

    return snap


def build_prompt(
    *,
    snap: dict[str, Any],
    color_name: str,
    background_preset: str,
    angle: str,
    time_of_day: str,
    render_profile: dict[str, str],
) -> str:
    """Build the final image generation prompt."""

    trim_name = str(snap.get("trimName") or "")
    year = snap.get("year")
    body_style = snap.get("bodyStyle")
    driven_wheels = snap.get("drivenWheels")
    hp = snap.get("hp")
    redline = snap.get("redline")

    descriptors: list[str] = [
        f"Photorealistic, ultra-detailed professional automotive photography.",
        f"A Porsche {trim_name}",
    ]

    if isinstance(year, int):
        descriptors[-1] += f" ({year})"

    descriptors[-1] += f" in {color_name} exterior paint."

    factual_bits: list[str] = []
    if body_style:
        factual_bits.append(f"Body style: {body_style}.")
    if driven_wheels:
        factual_bits.append(f"Drivetrain: {driven_wheels}.")
    if isinstance(hp, (int, float)):
        factual_bits.append(f"Power: {int(hp)} hp.")
    if isinstance(redline, (int, float)):
        factual_bits.append(f"Redline: {int(redline)} rpm.")

    visual_bits: list[str] = [
        f"Background: {_pretty_preset(background_preset)}.",
        f"Camera angle: {_pretty_preset(angle)}.",
        f"Lighting: {_pretty_preset(time_of_day)}.",
    ]

    style_bits: list[str] = [
        f"Render profile: {render_profile['stance']} stance; {render_profile['mood']} mood; {render_profile['shotStyle']} shot style; {render_profile['lens']} lens.",
        "Natural reflections, accurate paint metallic flake, realistic shadows, realistic wheel/tire details.",
        "No text, no logos, no watermarks, no UI overlays.",
    ]

    return " ".join(descriptors + factual_bits + visual_bits + style_bits)


class DreamService:
    """Generates Dream Porsche images via OpenAI Images API."""

    def __init__(self, db: AsyncDatabase, openai_client: OpenAIClient) -> None:
        self._db = db
        self._openai_client = openai_client

    async def generate(self, request: DreamRequest) -> DreamResponse:
        ranked_axes: list[str] = []
        if request.profile and request.profile.rankedAxes:
            ranked_axes = list(request.profile.rankedAxes)

        render_profile = _derive_render_profile_top2(ranked_axes)

        snap = await get_trim_snapshot(self._db, request.trimId)

        prompt = build_prompt(
            snap=snap,
            color_name=request.visual.colorName,
            background_preset=request.visual.backgroundPreset,
            angle=request.visual.angle,
            time_of_day=request.visual.timeOfDay,
            render_profile=render_profile,
        )

        image_url = await self._openai_client.generate_image(
            prompt=prompt,
            size=request.size,
        )

        meta: dict[str, Any] | None = {
            "size": request.size,
            "trimId": request.trimId,
            "year": snap.get("year"),
            "market": snap.get("market"),
        }

        return DreamResponse(
            imageUrl=image_url,
            promptUsed=prompt,
            renderProfile=render_profile,
            meta=meta,
        )
