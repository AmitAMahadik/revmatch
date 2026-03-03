"""Shortlist and Top Pick routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import PyMongoError

from app.dependencies.auth import require_user_id
from app.repositories.shortlist_repo import ShortlistRepo
from app.repositories.user_prefs_repo import UserPrefsRepo
from app.schemas.shortlist import (
    ShortlistAddRequest,
    ShortlistDeleteResponse,
    ShortlistItemResponse,
    ShortlistListResponse,
    TopPickClearResponse,
    TopPickRef,
    TopPickSetResponse,
)

router = APIRouter()

DB_UNAVAILABLE = {
    "error": {"type": "db_unavailable", "message": "Database temporarily unavailable"}
}


def _get_repos(request: Request) -> tuple[ShortlistRepo, UserPrefsRepo]:
    db = request.app.state.db
    return ShortlistRepo(db), UserPrefsRepo(db)


def _doc_to_item_response(doc: dict) -> ShortlistItemResponse:
    return ShortlistItemResponse(
        id=str(doc["_id"]),
        userId=doc["userId"],
        type=doc["type"],
        refId=doc["refId"],
        createdAt=doc["createdAt"],
    )


@router.post("", response_model=ShortlistItemResponse)
async def add_item(
    body: ShortlistAddRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
) -> ShortlistItemResponse:
    """Idempotent add: if item exists, return existing."""
    shortlist_repo, _ = _get_repos(request)
    try:
        doc = await shortlist_repo.insert_if_not_exists(
            user_id, body.type, body.refId
        )
        return _doc_to_item_response(doc)
    except PyMongoError:
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE)


@router.get("", response_model=ShortlistListResponse)
async def list_items(
    request: Request,
    user_id: str = Depends(require_user_id),
    type: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> ShortlistListResponse:
    """List shortlist items with optional type filter and pagination."""
    shortlist_repo, prefs_repo = _get_repos(request)
    try:
        prefs_doc = await prefs_repo.get_top_pick(user_id)
        top_pick = None
        if prefs_doc and prefs_doc.get("topPick"):
            tp = prefs_doc["topPick"]
            top_pick = TopPickRef(type=tp["type"], refId=tp["refId"])

        items, next_cursor = await shortlist_repo.list_by_user(
            user_id, item_type=type, limit=limit, cursor=cursor
        )
        return ShortlistListResponse(
            topPick=top_pick,
            items=[_doc_to_item_response(d) for d in items],
            nextCursor=next_cursor,
        )
    except PyMongoError:
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE)


@router.put("/top-pick", response_model=TopPickSetResponse)
async def set_top_pick(
    body: ShortlistAddRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
) -> TopPickSetResponse:
    """Set top pick. Ref must exist in shortlist for user."""
    shortlist_repo, prefs_repo = _get_repos(request)
    try:
        exists = await shortlist_repo.find_by_user_type_ref(
            user_id, body.type, body.refId
        )
        if not exists:
            raise HTTPException(
                status_code=404,
                detail={"error": {"type": "not_found", "message": "Item not in shortlist"}},
            )
        await prefs_repo.set_top_pick(user_id, body.type, body.refId)
        return TopPickSetResponse(topPick=TopPickRef(type=body.type, refId=body.refId))
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE)


@router.delete("/top-pick", response_model=TopPickClearResponse)
async def clear_top_pick(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> TopPickClearResponse:
    """Clear top pick for user."""
    _, prefs_repo = _get_repos(request)
    try:
        await prefs_repo.clear_top_pick(user_id)
        return TopPickClearResponse()
    except PyMongoError:
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE)


@router.delete("/{item_type}/{ref_id}", response_model=ShortlistDeleteResponse)
async def delete_item(
    item_type: str,
    ref_id: str,
    request: Request,
    user_id: str = Depends(require_user_id),
) -> ShortlistDeleteResponse:
    """Delete item if present. If it was topPick, clear topPick."""
    shortlist_repo, prefs_repo = _get_repos(request)
    try:
        deleted = await shortlist_repo.delete_by_user_type_ref(
            user_id, item_type, ref_id
        )
        top_pick_cleared = False
        if deleted:
            prefs_doc = await prefs_repo.get_top_pick(user_id)
            top_pick = prefs_doc.get("topPick") if prefs_doc else None
            if top_pick and top_pick.get("type") == item_type and top_pick.get("refId") == ref_id:
                await prefs_repo.clear_top_pick(user_id)
                top_pick_cleared = True
        return ShortlistDeleteResponse(deleted=deleted, topPickCleared=top_pick_cleared)
    except PyMongoError:
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE)
