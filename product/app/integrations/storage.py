"""CV object storage (phase 1 design section 6).

- S3Storage: any S3 compatible store (MinIO locally). Every object is written with server
  side encryption, and `head` reports it so a test can prove it.
- MemoryStorage: for tests; can be told to fail.
No public or presigned URLs exist. Keys are random and carry no personal data.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str
    encrypted: bool


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def head(self, key: str) -> ObjectInfo | None: ...


def new_cv_key(candidate_id: uuid.UUID) -> str:
    return f"cvs/{candidate_id}/{secrets.token_hex(16)}"


@dataclass
class MemoryStorage:
    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    fail_puts: bool = False
    fail_deletes: int = 0

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail_puts:
            raise StorageError("storage unavailable (test)")
        self.objects[key] = (data, content_type)

    async def delete(self, key: str) -> None:
        if self.fail_deletes > 0:
            self.fail_deletes -= 1
            raise StorageError("delete failed (test)")
        self.objects.pop(key, None)

    async def head(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        data, ct = self.objects[key]
        return ObjectInfo(size=len(data), content_type=ct, encrypted=True)


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "ap-southeast-2",
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=20
            ),
        )

    async def ensure_bucket(self, wait_seconds: float = 30.0) -> None:
        """Create the bucket if missing. Retries while the store starts up (the MinIO
        image has no shell for a container healthcheck)."""
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            try:
                await self._ensure_once()
                return
            except Exception as exc:
                if asyncio.get_running_loop().time() >= deadline:
                    raise StorageError(f"storage not reachable: {type(exc).__name__}") from exc
                await asyncio.sleep(1.0)

    async def _ensure_once(self) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except Exception:
                self._client.create_bucket(Bucket=self.bucket)
            if not self._is_minio():  # MinIO buckets are private unless a policy is added
                self._client.put_public_access_block(
                    Bucket=self.bucket,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    },
                )

        await asyncio.to_thread(_ensure)

    def _is_minio(self) -> bool:
        return "amazonaws.com" not in str(self._client.meta.endpoint_url)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
        except Exception as exc:
            raise StorageError(f"could not store object: {type(exc).__name__}") from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"could not delete object: {type(exc).__name__}") from exc

    async def head(self, key: str) -> ObjectInfo | None:
        def _head() -> ObjectInfo | None:
            try:
                r = self._client.head_object(Bucket=self.bucket, Key=key)
            except self._client.exceptions.ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                    return None
                raise
            return ObjectInfo(
                size=int(r["ContentLength"]),
                content_type=str(r.get("ContentType", "")),
                encrypted=bool(r.get("ServerSideEncryption")),
            )

        try:
            return await asyncio.to_thread(_head)
        except Exception as exc:
            raise StorageError(f"could not read object info: {type(exc).__name__}") from exc


async def delete_with_retry(storage: Storage, key: str, attempts: int = 3) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            await storage.delete(key)
            return True
        except StorageError:
            log.warning("storage delete attempt %d failed for a cv object", attempt)
            await asyncio.sleep(0.2 * attempt)
    return False


def make_storage(settings: Any) -> Storage:
    if settings.storage_backend == "memory":
        return MemoryStorage()
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise StorageError("S3 storage needs S3_ACCESS_KEY and S3_SECRET_KEY")
    return S3Storage(
        endpoint_url=settings.s3_endpoint_url or None,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        region=settings.s3_region,
    )
