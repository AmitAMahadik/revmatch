"""Thin service that delegates explanation generation to OpenAIClient."""

from __future__ import annotations

from app.clients.openai_client import OpenAIClient


class ExplanationService:
    """Generates explanations for recommendation results via OpenAI."""

    def __init__(self, openai_client: OpenAIClient) -> None:
        self._openai_client = openai_client

    async def explain(
        self, prompt: str, items: list[dict], parsed_query: dict
    ) -> str:
        """Generate an enthusiast-friendly explanation for the given items and query."""
        return await self._openai_client.generate_explanation(
            prompt, items, parsed_query
        )
