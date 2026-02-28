"""Chat service: orchestrates session, FindNext vs chat-only flow, and response building."""

from __future__ import annotations

from typing import Any, cast

from pymongo.asynchronous.database import AsyncDatabase

from app.clients.openai_client import OpenAIClient
from app.repositories.chat_session_repo import ChatSessionRepo
from app.services import recommendations_service
from app.services.card_builder import build_recommendation_cards
from app.services.preferences_score_service import score_preferences
from app.schemas.preferences import PreferencesScoreConstraints
from app.services.query_parser_service import QueryParserService

FIND_NEXT_KEYWORDS = frozenset(
    {
        "find",
        "next",
        "recommend",
        "compare",
        "manual",
        "rwd",
        "awd",
        "rev",
        "daily",
        "track",
        "best",
        "top",
    }
)

PREFERENCE_CONTEXT_KEYS = frozenset(
    {"manualOnly", "drivenWheels", "year", "limit", "rankedAxes", "minScores", "constraints"}
)


def _should_run_find_next(message: str, context: dict | None) -> bool:
    """True if we should run the FindNext flow based on message or context."""
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in FIND_NEXT_KEYWORDS):
        return True
    if not context:
        return False
    return bool(PREFERENCE_CONTEXT_KEYS & set(context.keys()))


def _should_run_preferences_score(context: dict | None) -> bool:
    """True if UI provided ranked axes; preference scoring is deterministic."""
    if not context:
        return False
    ranked = context.get("rankedAxes")
    return isinstance(ranked, list) and len(ranked) > 0


def _constraints_from_session_context(session_context: dict) -> dict:
    """Build QueryParserService constraints from merged session context."""
    constraints: dict[str, Any] = {}
    # US-only for now; allow override if explicitly set in session context.
    constraints["market"] = session_context.get("market") or "US"
    if session_context.get("year") is not None:
        constraints["year"] = session_context["year"]
    if session_context.get("limit") is not None:
        constraints["limit"] = session_context["limit"]
    if session_context.get("drivenWheels") is not None:
        constraints["drivenWheels"] = session_context["drivenWheels"]
    if session_context.get("manualOnly") is True:
        constraints["transmission"] = "Manual"
    return constraints


def _preference_constraints_from_session_context(session_context: dict) -> dict[str, Any]:
    """Build PreferencesScoreConstraints from merged session context.

    Precedence:
      - session_context["constraints"] (if present) is the base
      - then override with top-level convenience fields (market/year/drivenWheels/manualOnly/limit)
    """
    base = session_context.get("constraints")
    constraints: dict[str, Any] = dict(base) if isinstance(base, dict) else {}

    # US-only for now; allow override if explicitly set.
    constraints["market"] = session_context.get("market") or constraints.get("market") or "US"

    if session_context.get("year") is not None:
        constraints["year"] = session_context["year"]
    if session_context.get("limit") is not None:
        constraints["limit"] = session_context["limit"]
    if session_context.get("drivenWheels") is not None:
        constraints["drivenWheels"] = session_context["drivenWheels"]
    if session_context.get("manualOnly") is True:
        constraints["transmission"] = "Manual"

    return constraints


async def _call_score_preferences(
    *,
    db: AsyncDatabase,
    ranked_axes: list[str],
    min_scores: Any,
    constraints: dict[str, Any] | PreferencesScoreConstraints,
) -> dict[str, Any]:
    """Call score_preferences and normalize its output.

    score_preferences expects a PreferencesScoreConstraints model (attribute access like .limit).
    The chat layer may build constraints as a dict, so we normalize here.
    """
    constraints_model: PreferencesScoreConstraints
    if isinstance(constraints, PreferencesScoreConstraints):
        constraints_model = constraints
    else:
        # Defensive: ensure dict-like input
        constraints_dict: dict[str, Any] = constraints if isinstance(constraints, dict) else {}
        constraints_model = PreferencesScoreConstraints(**constraints_dict)

    result: Any
    try:
        result = await score_preferences(
            db=db,
            ranked_axes=ranked_axes,
            min_scores=min_scores,
            constraints=constraints_model,
        )
    except TypeError:
        # Fallback for positional signature
        result = await score_preferences(
            db,
            ranked_axes=ranked_axes,
            min_scores=min_scores,
            constraints=constraints_model,
        )

    # Normalize return: some implementations return (items, weights, filters)
    if isinstance(result, tuple) and len(result) == 3:
        items, weights_used, filters_used = result
        return {
            "items": items or [],
            "weightsUsed": weights_used or {},
            "filtersUsed": filters_used or {},
        }

    # Assume dict-like result
    out: dict[str, Any] = result if isinstance(result, dict) else {}
    return out


def _to_str(v: Any) -> str:
    """Convert value to string, handling ObjectId."""
    if v is None:
        return ""
    return str(v)


class ChatService:
    """Orchestrates chat sessions, FindNext vs chat-only flow, and response building."""

    def __init__(self, db: AsyncDatabase, openai_client: OpenAIClient) -> None:
        self._db = db
        self._openai_client = openai_client
        self._session_repo = ChatSessionRepo(db)
        self._query_parser = QueryParserService(openai_client)

    async def chat(
        self, session_id: str | None, message: str, context: dict | None
    ) -> dict:
        """Process a chat message and return a ChatResponse-shaped dict."""
        # 1) Load or create session. Merge request context into session context.
        if session_id:
            session = await self._session_repo.get(session_id)
        else:
            session = None

        if session is None:
            session = await self._session_repo.create(context)
            session_id = str(session["_id"])
        else:
            session_id = str(session["_id"])
            # Merge request context into session context (request overrides)
            merged = dict(session.get("context") or {})
            if context:
                merged.update(context)
            if merged != (session.get("context") or {}):
                await self._session_repo.update_context(session_id, merged)
            session["context"] = merged

        session_context = session.get("context") or {}
        last_parsed_query = session.get("lastParsedQuery")
        last_used_trim_ids = session.get("lastUsedTrimIds") or []

        # 2) Append user message to history.
        await self._session_repo.append_messages(
            session_id,
            [{"role": "user", "content": message}],
        )

        # 3) Decide deterministic preference scoring vs FindNext vs chat-only.
        if _should_run_preferences_score(session_context):
            # Preference-scoring flow (deterministic, driven by UI rankedAxes/minScores)
            ranked_axes = session_context.get("rankedAxes") or []
            min_scores = session_context.get("minScores")
            constraints = _preference_constraints_from_session_context(session_context)

            result = await _call_score_preferences(
                db=self._db,
                ranked_axes=ranked_axes,
                min_scores=min_scores,
                constraints=constraints,
            )

            items = result.get("items") or []
            weights_used = result.get("weightsUsed") or {}
            filters_used = result.get("filtersUsed") or {}

            # Build a parsed_query-like object for card/UI consistency.
            parsed_query = {
                "filters": filters_used,
                "weights": weights_used,
                "limit": constraints.get("limit", 10),
                "source": "preferences_score",
            }

            assistant_text = await self._openai_client.generate_explanation(
                message, items, parsed_query
            )
            cards = build_recommendation_cards(items, parsed_query)
            used_trim_ids = [_to_str(i.get("trimId")) for i in items]
            await self._session_repo.set_last_results(session_id, parsed_query, used_trim_ids)

        elif _should_run_find_next(message, session_context):
            # FindNext flow
            constraints = _constraints_from_session_context(session_context)
            parsed_query = await self._query_parser.parse(message, constraints)

            # Enforce precedence: if UI explicitly provided minScores, prefer it over LLM output.
            ui_min_scores = session_context.get("minScores")
            if isinstance(ui_min_scores, dict):
                parsed_filters = parsed_query.get("filters") or {}
                parsed_filters["minScores"] = ui_min_scores
                parsed_query["filters"] = parsed_filters

            items = await recommendations_service.find_next(self._db, parsed_query)
            assistant_text = await self._openai_client.generate_explanation(
                message, items, parsed_query
            )
            cards = build_recommendation_cards(items, parsed_query)
            used_trim_ids = [_to_str(i.get("trimId")) for i in items]
            await self._session_repo.set_last_results(
                session_id, parsed_query, used_trim_ids
            )

        else:
            # Chat-only flow
            assistant_text = await self._openai_client.generate_chat_reply(
                message,
                session_context,
                last_parsed_query=last_parsed_query,
                last_used_trim_ids=last_used_trim_ids,
            )
            cards = []
            used_trim_ids = []

        # 4) Append assistant message to history.
        await self._session_repo.append_messages(
            session_id,
            [{"role": "assistant", "content": assistant_text}],
        )

        # 5) Return ChatResponse-shaped dict.
        return {
            "sessionId": session_id,
            "assistantMessage": assistant_text,
            "cards": cards,
            "usedTrimIds": used_trim_ids,
        }
