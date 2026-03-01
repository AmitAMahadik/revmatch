"""S3 client for dream image upload and signed URL generation."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings


class S3Client:
    """Upload dream images to S3 and generate presigned URLs."""

    def __init__(self) -> None:
        self._client: Any = None  # boto3.client when S3 configured
        self._bucket: str | None = None
        self._region: str | None = None
        self._init_client()

    def _init_client(self) -> None:
        settings = get_settings()
        if not settings.has_s3():
            return
        import boto3  # pyright: ignore[reportMissingImports]

        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self._bucket = settings.s3_dream_bucket
        self._region = settings.aws_region

    def is_configured(self) -> bool:
        return self._client is not None and self._bucket is not None

    async def upload_dream_image(
        self, user_id: str, job_id: str, image_bytes: bytes
    ) -> str:
        """Upload image to S3. Returns storage key (e.g. dreams/{userId}/{jobId}.png)."""
        if not self.is_configured() or self._client is None or self._bucket is None:
            raise RuntimeError("S3 client not configured")
        key = f"dreams/{user_id}/{job_id}.png"
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=image_bytes,
            ContentType="image/png",
        )
        return key

    async def get_signed_url(self, storage_key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for the object."""
        if not self.is_configured() or self._client is None or self._bucket is None:
            raise RuntimeError("S3 client not configured")
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=expires_in,
        )
        return url
