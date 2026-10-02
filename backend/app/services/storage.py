"""Workbook file storage: a local folder, or any S3-compatible bucket (Backblaze B2, Cloudflare R2, AWS S3, MinIO).

The bucket is used on hosts without a persistent disk (e.g. Render Free). Objects are written with server-side
encryption where the provider supports it, and are never public - they are only reachable through the API.
"""
from __future__ import annotations

import contextlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import Iterator

from .. import config

log = logging.getLogger("ordertrack.storage")


class LocalStorage:
    name = "local"

    def put(self, src: Path, key: str) -> None:
        shutil.move(str(src), config.FILES_DIR / key)

    @contextlib.contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        yield config.FILES_DIR / key

    def iter_bytes(self, key: str, chunk: int = 1 << 20) -> Iterator[bytes]:
        with (config.FILES_DIR / key).open("rb") as f:
            while data := f.read(chunk):
                yield data

    def delete(self, key: str) -> None:
        (config.FILES_DIR / key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return (config.FILES_DIR / key).exists()


class S3Storage:
    name = "s3"

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config
        self.bucket = config.S3_BUCKET
        self.prefix = config.S3_PREFIX
        self.client = boto3.client(
            "s3", endpoint_url=config.S3_ENDPOINT_URL, region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY_ID, aws_secret_access_key=config.S3_SECRET_ACCESS_KEY,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, signature_version="s3v4",
                          request_checksum_calculation="when_required", response_checksum_validation="when_required"),
        )
        self._sse = True

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def put(self, src: Path, key: str) -> None:
        extra = {"ServerSideEncryption": "AES256"} if self._sse else {}
        try:
            self.client.upload_file(str(src), self.bucket, self._k(key), ExtraArgs=extra)
        except Exception as e:  # some S3-compatible providers reject the SSE header: retry without it
            if not extra:
                raise
            log.warning("bucket rejected server-side encryption header (%s); provider encrypts at rest by default", e)
            self._sse = False
            self.client.upload_file(str(src), self.bucket, self._k(key))
        src.unlink(missing_ok=True)

    @contextlib.contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        tmp = config.TMP_DIR / f"{uuid.uuid4().hex}{Path(key).suffix}"
        try:
            self.client.download_file(self.bucket, self._k(key), str(tmp))
            yield tmp
        finally:
            tmp.unlink(missing_ok=True)

    def iter_bytes(self, key: str, chunk: int = 1 << 20) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"]
        try:
            yield from body.iter_chunks(chunk)
        finally:
            body.close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except Exception:  # noqa: BLE001
            return False

    def check(self) -> None:
        """Fail fast at start-up if the bucket is unreachable or the keys are wrong."""
        self.client.head_bucket(Bucket=self.bucket)


_store: LocalStorage | S3Storage | None = None


def get() -> LocalStorage | S3Storage:
    global _store
    if _store is None:
        _store = S3Storage() if config.STORAGE_BACKEND == "s3" else LocalStorage()
    return _store
