"""FastAPI app: configure middleware up-front, manage PyMongo async client in lifespan, mount routes."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pymongo import AsyncMongoClient
from starlette.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import find_next, health, recommendations


def _parse_cors_origins_from_env() -> list[str]:
    """Parse CORS_ORIGINS from env without instantiating Settings (which requires MONGODB_URL)."""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [p.strip() for p in raw.split(",") if p.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    client = AsyncMongoClient(settings.mongodb_url)
    app.state.mongo_client = client
    app.state.db = client[settings.db_name]

    try:
        yield
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
