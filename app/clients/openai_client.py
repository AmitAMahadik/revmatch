"""Minimal async OpenAI client using httpx and the Responses API. No SDK."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any, cast

import httpx

from app.config import get_settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenAIClientError(Exception):
    """Raised when OpenAI API fails, returns non-JSON, or validation fails."""


def _extract_text(response_json: dict) -> str:
    """Extract the model's final text string from the Responses API response."""
    output = response_json.get("output") or []
    parts: list[str] = []

    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            ctype = content.get("type")
            if ctype == "refusal":
                msg = content.get("refusal", "Model refused the request")
                raise OpenAIClientError(f"OpenAI refusal: {msg}")
            if ctype == "output_text":
                text = content.get("text", "")
                if text:
                    parts.append(text)

    if not parts:
        raise OpenAIClientError("OpenAI response contained no output text")
    return "".join(parts)


def _extract_json(response_json: dict) -> dict:
    """Extract structured JSON from a Responses API response.

    Prefer structured JSON content if present; fall back to parsing output_text.
    """
    output = response_json.get("output") or []

    # Prefer structured output if the API returns it.
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            ctype = content.get("type")
            # Some Responses API variants return JSON content directly.
            if ctype in {"output_json", "json"} and isinstance(content.get("json"), dict):
                return content["json"]

    # Fallback: parse JSON from output_text.
    text = _extract_text(response_json)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise OpenAIClientError(f"OpenAI returned invalid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise OpenAIClientError("OpenAI returned non-dict JSON")
    return parsed


# JSON Schema for parse_query output (Product Intelligence query shape)
PARSE_QUERY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "filters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "market": {"type": "string", "enum": ["US"], "default": "US"},
                "year": {"type": ["integer", "null"], "minimum": 1990, "maximum": 2030},
                "drivenWheels": {
                    "type": ["string", "null"],
                    "enum": ["RWD", "AWD", None],
                },
                "transmission": {
                    "type": ["string", "null"],
                    "enum": ["Manual", "PDK", None],
                },
                "minScores": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "revHappiness": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                                "acousticDrama": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                                "steeringFeel": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                                "dailyCompliance": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                                "trackReadiness": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                                "depreciationStability": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                            },
                            "required": [
                                "revHappiness",
                                "acousticDrama",
                                "steeringFeel",
                                "dailyCompliance",
                                "trackReadiness",
                                "depreciationStability",
                            ],
                            "anyOf": [
                                {"type": "object", "additionalProperties": False, "properties": {"revHappiness": {"not": {"type": "null"}}}, "required": ["revHappiness"]},
                                {"type": "object", "additionalProperties": False, "properties": {"acousticDrama": {"not": {"type": "null"}}}, "required": ["acousticDrama"]},
                                {"type": "object", "additionalProperties": False, "properties": {"steeringFeel": {"not": {"type": "null"}}}, "required": ["steeringFeel"]},
                                {"type": "object", "additionalProperties": False, "properties": {"dailyCompliance": {"not": {"type": "null"}}}, "required": ["dailyCompliance"]},
                                {"type": "object", "additionalProperties": False, "properties": {"trackReadiness": {"not": {"type": "null"}}}, "required": ["trackReadiness"]},
                                {"type": "object", "additionalProperties": False, "properties": {"depreciationStability": {"not": {"type": "null"}}}, "required": ["depreciationStability"]},
                            ],
                        },
                    ],
                },
            },
            "required": ["market", "year", "drivenWheels", "transmission", "minScores"],
        },
        "weights": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "revHappiness": {"type": "number", "minimum": 0, "maximum": 1},
                "steeringFeel": {"type": "number", "minimum": 0, "maximum": 1},
                "acousticDrama": {"type": "number", "minimum": 0, "maximum": 1},
                "dailyCompliance": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["revHappiness", "steeringFeel", "acousticDrama", "dailyCompliance"],
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
    },
    "required": ["filters", "weights", "limit"],
}


class OpenAIClient:
    """Async OpenAI client using httpx. Responses API only."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise OpenAIClientError("OPENAI_API_KEY is not set")
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com",
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=60.0, pool=5.0),
        )

    async def __aenter__(self) -> OpenAIClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        backoff_delays = [0.5, 1.5]

        for attempt in range(3):
            try:
                response = await self._client.post("/v1/responses", json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status not in RETRYABLE_STATUS_CODES:
                    body = ""
                    try:
                        body = e.response.text[:500] if e.response.text else ""
                    except Exception:
                        pass
                    raise OpenAIClientError(
                        f"OpenAI API error {status}: {body}"
                    ) from e
                if attempt < 2:
                    delay = backoff_delays[attempt] + random.uniform(0, 0.1)
                    await asyncio.sleep(delay)
                else:
                    body = ""
                    try:
                        body = e.response.text[:500] if e.response.text else ""
                    except Exception:
                        pass
                    raise OpenAIClientError(
                        f"OpenAI API error {status}: {body}"
                    ) from e
            except httpx.RequestError as e:
                raise OpenAIClientError(f"OpenAI request failed: {e}") from e

        raise AssertionError("unreachable")  # Loop always returns or raises

    async def parse_query(self, prompt: str, constraints: dict) -> dict:
        """Parse user prompt into structured query dict. Returns JSON dict only."""
        constraints_str = json.dumps(constraints) if constraints else "{}"
        instructions = (
            "Parse the user's natural language query into a structured JSON object that MUST match the provided JSON schema. "
            "Use the following constraints as hints for defaults and valid ranges: "
            f"{constraints_str}. "
            "Return an object with exactly these top-level keys: filters, weights, limit. "
            "filters must include market (always 'US') and may include year (or null), drivenWheels ('RWD'/'AWD' or null), "
            "transmission ('Manual'/'PDK' or null), and minScores (object or null). "
            "IMPORTANT: If minScores is an object (not null), it MUST include ALL of these keys: revHappiness, acousticDrama, steeringFeel, dailyCompliance, trackReadiness, depreciationStability. Use null for any thresholds the user did not specify. At least one of the six keys MUST have a non-null value (do not use an object with all nulls). "
            "weights must include revHappiness, steeringFeel, acousticDrama, dailyCompliance as numbers between 0 and 1, and they should sum to 1. "
            "If the user does not specify weights, use a sensible default that sums to 1 (revHappiness 0.45, steeringFeel 0.25, acousticDrama 0.20, dailyCompliance 0.10). "
            "limit must be an integer between 1 and 50 (default 10). "
            "Return only valid JSON and no additional text."
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "input": [
                {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instructions}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "parsed_query",
                    "strict": True,
                    "schema": PARSE_QUERY_SCHEMA,
                }
            },
        }
        result = await self._post(payload)
        parsed = _extract_json(result)
        if not isinstance(parsed, dict):
            raise OpenAIClientError("parse_query returned non-dict")

        # Normalize to “strict and complete” shape expected by PARSE_QUERY_SCHEMA.
        raw_filters = parsed.get("filters")
        if isinstance(raw_filters, dict):
            filters: dict[str, Any] = cast(dict[str, Any], raw_filters)
        else:
            filters = {}
        parsed["filters"] = filters

        # Ensure required filter keys exist (use nulls when unspecified).
        filters.setdefault("market", "US")
        filters.setdefault("year", None)
        filters.setdefault("drivenWheels", None)
        filters.setdefault("transmission", None)

        raw_min_scores = filters.get("minScores")
        if raw_min_scores is None:
            filters["minScores"] = None
        elif isinstance(raw_min_scores, dict):
            min_scores: dict[str, Any] = cast(dict[str, Any], raw_min_scores)
            # Ensure ALL required keys exist; use null for unspecified.
            for k in (
                "revHappiness",
                "acousticDrama",
                "steeringFeel",
                "dailyCompliance",
                "trackReadiness",
                "depreciationStability",
            ):
                min_scores.setdefault(k, None)
            filters["minScores"] = min_scores
        else:
            # Invalid shape; force null.
            filters["minScores"] = None

        return parsed

    async def generate_explanation(
        self, prompt: str, results: list[dict], parsed_query: dict
    ) -> str:
        """Produce a concise enthusiast-friendly explanation grounded only in results and parsed_query."""
        results_str = json.dumps(results, default=str)
        parsed_str = json.dumps(parsed_query, default=str)
        instructions = (
            "You are an enthusiastic assistant. Generate a concise, friendly explanation "
            "of the search results for the user. You MUST only reference fields that exist "
            "in the provided 'results' and 'parsed_query' data. Do NOT invent any specs, "
            "numbers, or attributes. Be grounded strictly in the provided data."
        )
        user_content = (
            f"Original user prompt: {prompt}\n\n"
            f"Parsed query: {parsed_str}\n\n"
            f"Search results: {results_str}\n\n"
            "Write a short, enthusiast-friendly explanation of these results."
        )
        payload = {
            "model": self._model,
            "input": [
                {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instructions}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": user_content}]},
            ],
        }
        result = await self._post(payload)
        return _extract_text(result)

    async def generate_chat_reply(
        self,
        message: str,
        session_context: dict,
        last_parsed_query: dict | None = None,
        last_used_trim_ids: list[str] | None = None,
    ) -> str:
        """Generate a conversational reply for chat-only flow (no FindNext).

        Uses session context and optionally last search results for continuity.
        """
        context_str = json.dumps(session_context, default=str) if session_context else "{}"
        instructions = (
            "You are an enthusiastic car enthusiast assistant helping users explore Porsche models. "
            "Be friendly, concise, and helpful. Use the session context to personalize your response. "
        )
        if last_parsed_query and last_used_trim_ids:
            instructions += (
                f"The user previously ran a search with query: {json.dumps(last_parsed_query, default=str)} "
                f"and saw {len(last_used_trim_ids)} results. You may reference this if relevant."
            )
        instructions += f"\n\nSession context: {context_str}"

        payload = {
            "model": self._model,
            "input": [
                {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instructions}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": message}]},
            ],
        }
        result = await self._post(payload)
        return _extract_text(result)
