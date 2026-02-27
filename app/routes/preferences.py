"""GET /v1/preferences/catalog and POST /v1/preferences/score."""

from fastapi import APIRouter, Request

from app.schemas.preferences import (
    PreferenceAxis,
    PreferencesCatalogResponse,
    PreferencesScoreRequest,
    PreferencesScoreResponse,
    ScoredRecommendationItem,
)
from app.services import preferences_score_service

router = APIRouter()

PREFERENCES_CATALOG: list[PreferenceAxis] = [
    PreferenceAxis(
        key="revHappiness",
        label="Rev Happiness",
        shortLabel="Revs",
        description="How rewarding it feels to chase the redline and explore the upper range of the powerband.",
        scaleMin=0,
        scaleMax=10,
        icon="tachometer",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
    PreferenceAxis(
        key="acousticDrama",
        label="Acoustic Drama",
        shortLabel="Sound",
        description="Importance of exhaust character, engine note, and emotional sound at speed.",
        scaleMin=0,
        scaleMax=10,
        icon="speaker.wave.3.fill",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
    PreferenceAxis(
        key="steeringFeel",
        label="Steering Feel",
        shortLabel="Steering",
        description="Precision, feedback, and connection through the steering wheel.",
        scaleMin=0,
        scaleMax=10,
        icon="steeringwheel",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
    PreferenceAxis(
        key="dailyCompliance",
        label="Daily Compliance",
        shortLabel="Daily",
        description="Comfort, usability, and livability for everyday driving.",
        scaleMin=0,
        scaleMax=10,
        icon="car.fill",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
    PreferenceAxis(
        key="trackReadiness",
        label="Track Readiness",
        shortLabel="Track",
        description="Capability, composure, and endurance under performance or track conditions.",
        scaleMin=0,
        scaleMax=10,
        icon="flag.checkered",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
    PreferenceAxis(
        key="depreciationStability",
        label="Depreciation Stability",
        shortLabel="Resale",
        description="Expected long-term value retention and market stability.",
        scaleMin=0,
        scaleMax=10,
        icon="chart.line.uptrend.xyaxis",
        defaultWeight=1 / 6,
        supportsMinThreshold=True,
    ),
]


@router.get("/catalog", response_model=PreferencesCatalogResponse)
async def get_catalog() -> PreferencesCatalogResponse:
    return PreferencesCatalogResponse(axes=PREFERENCES_CATALOG)


@router.post("/score", response_model=PreferencesScoreResponse)
async def post_score(
    request: Request, body: PreferencesScoreRequest
) -> PreferencesScoreResponse:
    items, weights_used, filters_used = await preferences_score_service.score_preferences(
        request.app.state.db,
        ranked_axes=body.rankedAxes,
        min_scores=body.minScores,
        constraints=body.constraints,
    )
    return PreferencesScoreResponse(
        items=[ScoredRecommendationItem.model_validate(i) for i in items],
        weightsUsed=weights_used,
        filtersUsed=filters_used,
    )
