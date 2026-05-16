"""MinIO object helpers for externally uploaded PDFs."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from server.config import ServerConfig


def _build_minio_client(config: ServerConfig):
    """Create a MinIO client from server configuration."""
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("minio package is required for MinIO operations") from exc

    return Minio(
        config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
    )


def parse_minio_path(minio_path: str) -> tuple[str, str]:
    """Parse `bucket/key` object paths from the external API contract."""
    value = minio_path.strip().removeprefix("s3://")
    bucket, sep, object_name = value.partition("/")
    if not sep or not bucket or not object_name:
        raise ValueError("minioPath must use bucket/key format")
    return bucket, object_name


def download_pdf_from_minio(
    *,
    minio_path: str,
    destination: Path,
    config: ServerConfig,
) -> None:
    """Download one PDF object from MinIO to a local destination path."""
    bucket, object_name = parse_minio_path(minio_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = _build_minio_client(config)
    client.fget_object(bucket, object_name, str(destination))


def upload_pdf_to_minio(
    *,
    bucket: str,
    object_name: str,
    content: bytes,
    config: ServerConfig,
) -> str:
    """Upload one PDF object to MinIO and return its `bucket/key` path."""
    if not bucket or not object_name:
        raise ValueError("bucket and object_name are required")

    client = _build_minio_client(config)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    client.put_object(
        bucket,
        object_name,
        BytesIO(content),
        length=len(content),
        content_type="application/pdf",
    )
    return f"{bucket}/{object_name}"
