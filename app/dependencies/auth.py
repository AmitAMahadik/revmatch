"""Auth dependencies for user-scoped endpoints.

Placeholder implementation: returns userId from X-User-Id header if present,
otherwise "anonymous". Replace with JWT/Firebase/etc. for production auth.

In non-dev (prod/staging): X-User-Id is required; "anonymous" is rejected.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.config import get_settings


async def get_current_user_id(request: Request) -> str:
    """Extract userId for request scoping.

    Dev: returns X-User-Id if present, else "anonymous".
    Non-dev: requires X-User-Id (401 if missing/blank); rejects "anonymous".
    """
    user_id = request.headers.get("X-User-Id", "").strip()
    if get_settings().env != "dev":
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="X-User-Id header required",
            )
        if user_id.lower() == "anonymous":
            raise HTTPException(
                status_code=401,
                detail="Anonymous not allowed",
            )
    return user_id or "anonymous"


async def require_user_id(request: Request) -> str:
    """Require X-User-Id header; return 400 if missing or blank."""
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={"error": {"type": "missing_user_id", "message": "X-User-Id header required"}},
        )
    return user_id
