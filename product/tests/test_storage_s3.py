"""Real S3 compatible storage (MinIO). Runs when S3_TEST=1 and the store is reachable;
CI starts MinIO for it. Proves objects are encrypted at rest and deletes work."""

from __future__ import annotations

import os
import uuid

import pytest

from app.config import Settings
from app.integrations.storage import S3Storage, new_cv_key

pytestmark = pytest.mark.skipif(
    os.environ.get("S3_TEST") != "1", reason="set S3_TEST=1 with MinIO running"
)


@pytest.fixture
async def store() -> S3Storage:
    s = Settings()  # reads .env locally, env vars in CI
    assert s.s3_access_key is not None and s.s3_secret_key is not None, "S3 keys not set"
    st = S3Storage(
        endpoint_url=s.s3_endpoint_url,
        bucket=f"{s.s3_bucket}-test",
        access_key=s.s3_access_key.get_secret_value(),
        secret_key=s.s3_secret_key.get_secret_value(),
        region=s.s3_region,
    )
    await st.ensure_bucket()
    return st


async def test_object_is_encrypted_at_rest_and_deletable(store: S3Storage) -> None:
    key = new_cv_key(uuid.uuid4())
    await store.put(key, b"%PDF-1.7\nsynthetic\n%%EOF\n", "application/pdf")
    info = await store.head(key)
    assert info is not None and info.size > 0
    assert info.encrypted, "server side encryption missing: is MINIO_KMS_SECRET_KEY set?"
    await store.delete(key)
    assert await store.head(key) is None


async def test_key_has_no_personal_data() -> None:
    key = new_cv_key(uuid.UUID(int=1))
    assert (
        key.startswith("cvs/00000000-0000-0000-0000-000000000001/")
        and len(key.split("/")[-1]) == 32
    )
