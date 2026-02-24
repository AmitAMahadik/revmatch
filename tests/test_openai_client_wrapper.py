"""Tests for OpenAIClient. No network calls; monkeypatch stubs httpx.AsyncClient.post to return fake Responses API JSON."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.clients.openai_client import OpenAIClient


# Fake Responses API payload for parse_query (JSON in output_text, fallback path)
FAKE_PARSE_QUERY_JSON = {
    "filters": {"market": "US", "year": 2024},
    "weights": {
        "revHappiness": 0.45,
        "steeringFeel": 0.25,
        "acousticDrama": 0.20,
        "dailyCompliance": 0.10,
    },
    "limit": 10,
}

FAKE_PARSE_QUERY_RESPONSE = {
    "output": [
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps(FAKE_PARSE_QUERY_JSON),
                }
            ],
        }
    ]
}

# Fake Responses API payload for parse_query (structured JSON content, preferred path)
FAKE_PARSE_QUERY_STRUCTURED_RESPONSE = {
    "output": [
        {
            "type": "message",
            "content": [
                {
                    "type": "json",
                    "json": FAKE_PARSE_QUERY_JSON,
                }
            ],
        }
    ]
}

# Fake Responses API payload for generate_explanation (text output)
FAKE_EXPLANATION_RESPONSE = {
    "output": [
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "These sports cars offer excellent rev happiness and steering feel.",
                }
            ],
        }
    ]
}


class FakeResponse:
    """Minimal httpx-like response for testing."""

    def __init__(self, json_payload: dict):
        self._json = json_payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json


class FakeAsyncClient:
    """Stub for httpx.AsyncClient; post returns the configured fake response."""

    def __init__(self, *args, **kwargs):
        self._response_payload: dict | None = None

    def set_response(self, payload: dict) -> None:
        self._response_payload = payload

    async def post(self, *args, **kwargs):
        if self._response_payload is None:
            raise RuntimeError("FakeAsyncClient.post called without set_response")
        return FakeResponse(self._response_payload)

    async def aclose(self) -> None:
        pass


@pytest.fixture
def mock_settings():
    """Provide fake settings so OpenAIClient can be instantiated without real env."""
    settings = MagicMock()
    settings.openai_api_key = "sk-fake-key"
    settings.openai_model = "gpt-4o-mini"
    return settings


def test_parse_query_returns_dict_matching_fake_json(monkeypatch, mock_settings):
    """parse_query returns a dict that matches the fake JSON content."""
    fake_http = FakeAsyncClient()
    fake_http.set_response(FAKE_PARSE_QUERY_RESPONSE)

    def fake_client_factory(*args, **kwargs):
        return fake_http

    monkeypatch.setattr("app.clients.openai_client.get_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.AsyncClient",
        fake_client_factory,
    )
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.Timeout",
        lambda *a, **kw: None,
    )

    client = OpenAIClient()

    async def _run():
        return await client.parse_query("sporty RWD coupes", {"market": "US"})

    result = asyncio.run(_run())

    assert result == FAKE_PARSE_QUERY_JSON
    assert result["filters"]["market"] == "US"
    assert result["filters"]["year"] == 2024
    assert result["weights"]["revHappiness"] == 0.45
    assert result["limit"] == 10


# Test for structured JSON content (preferred path)
def test_parse_query_prefers_structured_json_content(monkeypatch, mock_settings):
    """parse_query prefers structured JSON content when present."""
    fake_http = FakeAsyncClient()
    fake_http.set_response(FAKE_PARSE_QUERY_STRUCTURED_RESPONSE)

    def fake_client_factory(*args, **kwargs):
        return fake_http

    monkeypatch.setattr("app.clients.openai_client.get_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.AsyncClient",
        fake_client_factory,
    )
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.Timeout",
        lambda *a, **kw: None,
    )

    client = OpenAIClient()

    async def _run():
        return await client.parse_query("sporty RWD coupes", {"market": "US"})

    result = asyncio.run(_run())

    assert result == FAKE_PARSE_QUERY_JSON


def test_generate_explanation_returns_string_from_fake_response(
    monkeypatch, mock_settings
):
    """generate_explanation returns a string extracted from the fake response."""
    fake_http = FakeAsyncClient()
    fake_http.set_response(FAKE_EXPLANATION_RESPONSE)

    def fake_client_factory(*args, **kwargs):
        return fake_http

    monkeypatch.setattr("app.clients.openai_client.get_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.AsyncClient",
        fake_client_factory,
    )
    monkeypatch.setattr(
        "app.clients.openai_client.httpx.Timeout",
        lambda *a, **kw: None,
    )

    client = OpenAIClient()

    async def _run():
        return await client.generate_explanation(
            prompt="sporty cars",
            results=[{"trimName": "GTS 4.0"}],
            parsed_query={
                "filters": {"market": "US"},
                "weights": {
                    "revHappiness": 0.45,
                    "steeringFeel": 0.25,
                    "acousticDrama": 0.20,
                    "dailyCompliance": 0.10,
                },
                "limit": 10,
            },
        )

    result = asyncio.run(_run())

    expected_text = FAKE_EXPLANATION_RESPONSE["output"][0]["content"][0]["text"]
    assert result == expected_text
    assert "rev happiness" in result
    assert "steering feel" in result
