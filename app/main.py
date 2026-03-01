"""FastAPI app: configure middleware up-front, manage PyMongo async client in lifespan, mount routes."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pymongo import AsyncMongoClient
from starlette.middleware.cors import CORSMiddleware

from app.clients.openai_client import OpenAIClient
from app.clients.s3_client import S3Client
from app.config import get_settings
from app.routes import chat, dream, find_next, health, preferences, recommendations


def _parse_cors_origins_from_env() -> list[str]:
    """Parse CORS_ORIGINS from env without instantiating Settings (which requires MONGODB_URL)."""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [p.strip() for p in raw.split(",") if p.strip()]


async def _ensure_dream_renders_indexes(db):
    """Create dream_renders collection indexes if not present."""
    coll = db["dream_renders"]
    await coll.create_index([("userId", 1), ("createdAt", -1)])
    await coll.create_index([("userId", 1), ("promptHash", 1)])


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    client = AsyncMongoClient(settings.mongodb_url)
    app.state.mongo_client = client
    app.state.db = client[settings.db_name]

    openai_client = OpenAIClient()
    app.state.openai_client = openai_client

    s3_client = S3Client()
    app.state.s3_client = s3_client if s3_client.is_configured() else None

    await _ensure_dream_renders_indexes(app.state.db)

    try:
        yield
    finally:
        # Close OpenAI client first (it may have in-flight requests).
        try:
            await openai_client.aclose()
        finally:
            await client.close()


app = FastAPI(title="revmatch", lifespan=lifespan)

# Middleware must be added before the application starts.
_origins = _parse_cors_origins_from_env()
_allow_origins = ["*"] if "*" in _origins else _origins
app.add_middleware(
    CORSMiddleware,
    # If CORS_ORIGINS is unset, default to allow all for dev convenience.
    allow_origins=_allow_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, tags=["health"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
app.include_router(find_next.router, prefix="/v1", tags=["find-next"])
app.include_router(chat.router, prefix="/v1", tags=["chat"])
app.include_router(dream.router, prefix="/v1", tags=["dream"])
app.include_router(preferences.router, prefix="/v1/preferences", tags=["preferences"])
