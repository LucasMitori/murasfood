"""
Object storage abstraction.

Binary data never lives in PostgreSQL (spec §10). The application talks to this
interface; the concrete backend is chosen from settings, so development can use
the local filesystem or MinIO while production points at Cloudflare R2 or S3
without a single code change (ADR-004).

Private objects are served through *signed*, expiring URLs — never by making a
bucket public.
"""

from __future__ import annotations

import contextlib
import hashlib
import mimetypes
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO, TYPE_CHECKING
from urllib.parse import quote

from django.conf import settings

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator


class StorageError(RuntimeError):
    """Raised when the storage backend cannot complete an operation."""


class StorageBackend(ABC):
    """The contract every storage implementation must satisfy."""

    @abstractmethod
    def save(self, key: str, content: IO[bytes], *, content_type: str, public: bool) -> str:
        """Persist ``content`` under ``key`` and return the stored key."""

    @abstractmethod
    def open(self, key: str) -> IO[bytes]:
        """Return a readable stream for ``key``."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove ``key``. Missing objects are not an error."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def url(self, key: str, *, expires_in: int | None = None, public: bool = False) -> str:
        """Return a URL for ``key``.

        Private objects get a signed URL valid for ``expires_in`` seconds.
        """


class LocalFileSystemStorage(StorageBackend):
    """Development backend. Writes under ``MEDIA_ROOT``.

    Not suitable for production: a container filesystem is ephemeral, and two
    API replicas would not see each other's uploads.
    """

    def __init__(self, root: Path | None = None, base_url: str | None = None) -> None:
        self.root = Path(root or settings.MEDIA_ROOT)
        self.base_url = (base_url or settings.MEDIA_URL).rstrip("/")

    def _path(self, key: str) -> Path:
        # Reject traversal before touching the filesystem.
        safe = os.path.normpath(key).replace("\\", "/").lstrip("/")
        if safe.startswith("..") or "/../" in safe:
            raise StorageError(f"Unsafe storage key: {key!r}")
        return self.root / safe

    def save(self, key: str, content: IO[bytes], *, content_type: str, public: bool) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        content.seek(0)
        with open(target, "wb") as handle:
            shutil.copyfileobj(content, handle)
        return key

    def open(self, key: str) -> IO[bytes]:
        try:
            return open(self._path(key), "rb")
        except FileNotFoundError as exc:
            raise StorageError(f"Object not found: {key}") from exc

    def delete(self, key: str) -> None:
        # Deleting something that is already gone is the desired end state.
        with contextlib.suppress(FileNotFoundError):
            self._path(key).unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def url(self, key: str, *, expires_in: int | None = None, public: bool = False) -> str:
        return f"{self.base_url}/{quote(key)}"


class S3CompatibleStorage(StorageBackend):
    """Production backend for any S3-compatible service."""

    def __init__(self) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise StorageError("boto3 is required for S3 storage") from exc

        self.bucket = settings.S3_BUCKET
        self.default_ttl = settings.S3_SIGNED_URL_TTL_SECONDS
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT or None,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def save(self, key: str, content: IO[bytes], *, content_type: str, public: bool) -> str:
        content.seek(0)
        extra = {"ContentType": content_type}
        if public:
            extra["ACL"] = "public-read"
        self._client.upload_fileobj(content, self.bucket, key, ExtraArgs=extra)
        return key

    def open(self, key: str) -> IO[bytes]:
        import io

        buffer = io.BytesIO()
        self._client.download_fileobj(self.bucket, key, buffer)
        buffer.seek(0)
        return buffer

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return False
        return True

    def url(self, key: str, *, expires_in: int | None = None, public: bool = False) -> str:
        if public and settings.S3_PUBLIC_ENDPOINT:
            return f"{settings.S3_PUBLIC_ENDPOINT.rstrip('/')}/{self.bucket}/{quote(key)}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in or self.default_ttl,
        )


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the configured backend (memoised per process)."""
    global _backend
    if _backend is not None:
        return _backend

    choice = (settings.STORAGE_BACKEND or "auto").lower()
    if choice == "local" or (choice == "auto" and not settings.S3_ENDPOINT):
        _backend = LocalFileSystemStorage()
    else:
        _backend = S3CompatibleStorage()
    return _backend


def reset_storage_cache() -> None:
    """Drop the memoised backend. Used by tests that switch configuration."""
    global _backend
    _backend = None


# =============================================================================
# Helpers
# =============================================================================
def checksum(stream: IO[bytes], *, chunk_size: int = 65536) -> str:
    """SHA-256 of a stream, rewound afterwards.

    Stored with every asset so duplicate uploads can be detected and corruption
    caught on retrieval.
    """
    digest = hashlib.sha256()
    stream.seek(0)
    for chunk in iter(lambda: stream.read(chunk_size), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def build_key(*, tenant_id: str, folder: str, asset_id: str, filename: str) -> str:
    """Compose a collision-free, tenant-partitioned object key.

    Partitioning by tenant makes per-merchant export, deletion and cost
    attribution straightforward.
    """
    extension = Path(filename).suffix.lower()[:10]
    return f"{tenant_id}/{folder}/{asset_id}{extension}"


def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(filename)[0] or fallback


def iter_derivative_keys(key: str, sizes: Iterator[str]) -> dict[str, str]:
    """Derive the object keys for resized variants of an image."""
    stem, _, _extension = key.rpartition(".")
    return {name: f"{stem}_{name}.webp" for name in sizes} if stem else {}
