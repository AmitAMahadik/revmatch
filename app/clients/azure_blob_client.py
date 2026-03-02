"""Azure Blob Storage client for dream image upload and SAS URL generation."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    ContentSettings,
    generate_blob_sas,
)

logger = logging.getLogger(__name__)

CONTAINER_NAME = "dreams"


def _parse_account_key(conn_str: str) -> str:
    for part in conn_str.split(";"):
        if part.strip().startswith("AccountKey="):
            return part.split("=", 1)[1].strip()
    raise RuntimeError("AccountKey not found in connection string")


class AzureBlobClient:
    def __init__(self) -> None:
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        if not conn_str:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
        self._account_key = _parse_account_key(conn_str)
        self._service_client = BlobServiceClient.from_connection_string(conn_str)
        self._container_client = self._service_client.get_container_client(CONTAINER_NAME)

        # Ensure the container exists (idempotent)
        try:
            self._container_client.create_container()
        except ResourceExistsError:
            pass

    async def upload_dream_image(
        self, user_id: str, job_id: str, image_bytes: bytes
    ) -> str:
        blob_key = f"prod/{user_id}/{job_id}.png"
        blob_client = self._container_client.get_blob_client(blob_key)

        def _upload() -> None:
            blob_client.upload_blob(
                data=image_bytes,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type="image/png",
                    cache_control="public, max-age=31536000, immutable",
                ),
            )

        try:
            await asyncio.to_thread(_upload)
            logger.info("Uploaded dream image", extra={"blob_key": blob_key})
            return blob_key
        except Exception:
            logger.exception("Dream image upload failed", extra={"blob_key": blob_key})
            raise

    async def generate_signed_url(
        self, blob_key: str, expires_minutes: int = 60
    ) -> str:
        if expires_minutes <= 0:
            raise ValueError("expires_minutes must be > 0")
        account_name = self._service_client.account_name
        if not isinstance(account_name, str) or not account_name:
            raise RuntimeError("Storage account name not available")
        expiry = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=CONTAINER_NAME,
            blob_name=blob_key,
            account_key=self._account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_key}?{sas_token}"
        logger.info("Generated signed URL", extra={"blob_key": blob_key, "expires_minutes": expires_minutes})
        return url

    async def delete_blob(self, blob_key: str) -> None:
        blob_client = self._container_client.get_blob_client(blob_key)

        def _delete() -> None:
            blob_client.delete_blob()

        try:
            await asyncio.to_thread(_delete)
            logger.info("Deleted blob", extra={"blob_key": blob_key})
        except ResourceNotFoundError:
            logger.debug("Blob not found for delete", extra={"blob_key": blob_key})
        except Exception:
            logger.exception("Blob delete failed", extra={"blob_key": blob_key})
            raise

    async def blob_exists(self, blob_key: str) -> bool:
        blob_client = self._container_client.get_blob_client(blob_key)
        return await asyncio.to_thread(blob_client.exists)


if __name__ == "__main__":
    async def _main() -> None:
        client = AzureBlobClient()
        key = await client.upload_dream_image(
            "test-user",
            "test-job",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde",
        )
        url = await client.generate_signed_url(key, expires_minutes=60)
        print(url)

    asyncio.run(_main())
