#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

# Ensure repo root is on sys.path so `import app.*` works when executing from ./scripts
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if TYPE_CHECKING:
    from app.clients.azure_blob_client import AzureBlobClient

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection


MAX_IMAGE_BYTES_DEFAULT = 15_000_000  # 15 MB
MIGRATION_VERSION = "legacy_base64_to_azure_v1"

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def is_png(data: bytes) -> bool:
    return len(data) >= 8 and data[:8] == PNG_SIG


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_data_url_to_bytes(data_url: str) -> bytes:
    # Expected: data:image/png;base64,<b64>
    if not data_url.startswith("data:image/"):
        raise ValueError("not a data:image/* url")
    try:
        header, b64 = data_url.split(",", 1)
    except ValueError as e:
        raise ValueError(f"invalid data url: {e}") from e
    if ";base64" not in header:
        raise ValueError("data url is not base64 encoded")
    return base64.b64decode(b64)


def get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def mongo_connect(mongo_uri: str) -> MongoClient:
    return MongoClient(mongo_uri)


def get_collection(client: MongoClient, db_name: str, collection_name: str) -> Collection:
    return client[db_name][collection_name]


def build_blob_key(user_id: str, job_id: str) -> str:
    # Must match your runtime path scheme.
    return f"prod/{user_id}/{job_id}.png"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy base64 dream images in Mongo to Azure Blob")
    parser.add_argument("--mongo-uri-env", default="MDB_MCP_CONNECTION_STRING",
                        help="Env var containing Mongo connection string (default: MDB_MCP_CONNECTION_STRING)")
    parser.add_argument("--db", required=True, help="Mongo DB name (e.g., porsche)")
    parser.add_argument("--collection", default="dream_renders", help="Collection name (default: dream_renders)")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to process (0 = no limit)")
    parser.add_argument("--batch", type=int, default=100, help="Batch size for cursor (default: 100)")
    parser.add_argument("--max-bytes", type=int, default=MAX_IMAGE_BYTES_DEFAULT, help="Max decoded image size")
    parser.add_argument("--unset-image-url", action="store_true",
                        help="Unset imageUrl after successful migration (recommended)")
    parser.add_argument("--dry-run", action="store_true", help="Do not upload or update, only report")
    parser.add_argument("--only-png", action="store_true",
                        help="Only migrate data:image/png;base64,... (skip jpeg/webp)")
    args = parser.parse_args()

    mongo_uri = get_env(args.mongo_uri_env)

    # Azure client will throw if AZURE_STORAGE_CONNECTION_STRING is missing; allow dry-run without it.
    azure: Optional[object] = None
    if not args.dry_run:
        try:
            from app.clients.azure_blob_client import AzureBlobClient  # type: ignore
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Could not import app.clients.azure_blob_client. "
                "Ensure the repo root is on PYTHONPATH. "
                f"REPO_ROOT={REPO_ROOT} sys.path[0:3]={sys.path[0:3]}"
            ) from e
        azure = AzureBlobClient()

    client = mongo_connect(mongo_uri)
    coll = get_collection(client, args.db, args.collection)

    query: dict[str, Any] = {
        "storageKey": {"$exists": False},
        "imageUrl": {"$type": "string", "$regex": r"^data:image\/.*;base64,"},
    }
    if args.only_png:
        query["imageUrl"]["$regex"] = r"^data:image\/png;base64,"

    projection = {
        "_id": 1,
        "userId": 1,
        "imageUrl": 1,
        "storageKey": 1,
    }

    total_found = coll.count_documents(query)
    print(f"Found {total_found} legacy docs to migrate (query={query}).")

    cursor = coll.find(query, projection=projection, batch_size=args.batch).sort("_id", 1)
    processed = 0
    migrated = 0
    skipped = 0
    failed = 0

    for doc in cursor:
        if args.limit and processed >= args.limit:
            break
        processed += 1

        doc_id = doc.get("_id")
        user_id = doc.get("userId")
        image_url = doc.get("imageUrl")

        if not isinstance(doc_id, ObjectId):
            print(f"[SKIP] doc has non-ObjectId _id: {doc_id}")
            skipped += 1
            continue
        job_id = str(doc_id)

        if not isinstance(user_id, str) or not user_id:
            print(f"[FAIL] {job_id}: missing/invalid userId")
            failed += 1
            continue
        if not isinstance(image_url, str) or not image_url.startswith("data:image/"):
            print(f"[SKIP] {job_id}: missing/invalid imageUrl")
            skipped += 1
            continue

        # Optional: enforce png-only even if regex allowed others
        if args.only_png and not image_url.startswith("data:image/png;base64,"):
            print(f"[SKIP] {job_id}: not png data-url")
            skipped += 1
            continue

        try:
            image_bytes = parse_data_url_to_bytes(image_url)
        except Exception as e:
            print(f"[FAIL] {job_id}: base64 decode error: {e}")
            failed += 1
            continue

        if len(image_bytes) > args.max_bytes:
            print(f"[FAIL] {job_id}: image too large ({len(image_bytes)} > {args.max_bytes})")
            failed += 1
            continue

        if not is_png(image_bytes):
            # You can relax this if you truly stored jpeg/webp in the past.
            print(f"[FAIL] {job_id}: decoded bytes are not PNG (signature mismatch)")
            failed += 1
            continue

        storage_key = build_blob_key(user_id=user_id, job_id=job_id)

        if args.dry_run:
            print(f"[DRY] would upload {job_id} -> {storage_key} ({len(image_bytes)} bytes)")
            migrated += 1
            continue

        try:
            # Upload and rely on overwrite semantics to make reruns safe.
            uploaded_key = awaitable_run(getattr(azure, "upload_dream_image")(user_id, job_id, image_bytes))
            if uploaded_key != storage_key:
                print(f"[WARN] {job_id}: uploaded key differs: {uploaded_key} vs expected {storage_key}")
                storage_key = uploaded_key
        except Exception as e:
            print(f"[FAIL] {job_id}: azure upload failed: {e}")
            failed += 1
            continue

        update: dict[str, Any] = {
            "$set": {
                "storageKey": storage_key,
                "migratedAt": utc_now(),
                "migrationVersion": MIGRATION_VERSION,
            }
        }
        if args.unset_image_url:
            update["$unset"] = {"imageUrl": ""}

        result = coll.update_one({"_id": doc_id}, update)
        if result.modified_count != 1:
            print(f"[WARN] {job_id}: update did not modify document (matched={result.matched_count})")
        else:
            print(f"[OK] {job_id}: migrated -> {storage_key}")
        migrated += 1

    print("\nDone.")
    print(f"Processed: {processed}")
    print(f"Migrated:  {migrated}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    return 0


def awaitable_run(awaitable):
    """
    Runs an awaitable from sync script context.
    We avoid making the whole script async to keep it runnable with plain python.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If someone runs this inside an existing loop, fail fast.
        raise RuntimeError("This script must be run from a non-async context (no running event loop).")

    return asyncio.run(awaitable)


if __name__ == "__main__":
    raise SystemExit(main())