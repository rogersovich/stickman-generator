"""Cloudflare R2 Object Storage Client for Stickman Generator."""

import logging
import mimetypes
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from . import config

logger = logging.getLogger("r2")

_s3_client = None

def get_s3():
    global _s3_client
    if _s3_client is None:
        if not config.has_r2():
            raise RuntimeError("Cloudflare R2 credentials not configured")
        _s3_client = boto3.client(
            "s3",
            endpoint_url=config.R2_ENDPOINT_URL,
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"})
        )
    return _s3_client


def upload_file(local_path: Path, r2_key: str, content_type: Optional[str] = None) -> bool:
    if not config.has_r2() or not local_path.exists():
        return False
    if not content_type:
        content_type, _ = mimetypes.guess_type(str(local_path))
        content_type = content_type or "application/octet-stream"

    s3 = get_s3()
    try:
        s3.upload_file(
            str(local_path),
            config.R2_BUCKET_NAME,
            r2_key,
            ExtraArgs={"ContentType": content_type}
        )
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to R2 ({r2_key}): {e}")
        return False


def upload_bytes(data: bytes, r2_key: str, content_type: str = "application/octet-stream") -> bool:
    if not config.has_r2():
        return False
    s3 = get_s3()
    try:
        s3.put_object(
            Bucket=config.R2_BUCKET_NAME,
            Key=r2_key,
            Body=data,
            ContentType=content_type,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to put bytes to R2 ({r2_key}): {e}")
        return False


def download_file(r2_key: str, local_path: Path) -> bool:
    if not config.has_r2():
        return False
    s3 = get_s3()
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(config.R2_BUCKET_NAME, r2_key, str(local_path))
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        logger.error(f"Failed to download R2 {r2_key} to {local_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to download R2 {r2_key} to {local_path}: {e}")
        return False


def get_object_bytes(r2_key: str) -> Optional[bytes]:
    if not config.has_r2():
        return None
    s3 = get_s3()
    try:
        resp = s3.get_object(Bucket=config.R2_BUCKET_NAME, Key=r2_key)
        return resp["Body"].read()
    except Exception:
        return None


def file_exists(r2_key: str) -> bool:
    if not config.has_r2():
        return False
    s3 = get_s3()
    try:
        s3.head_object(Bucket=config.R2_BUCKET_NAME, Key=r2_key)
        return True
    except Exception:
        return False


def delete_object(r2_key: str) -> bool:
    if not config.has_r2():
        return False
    s3 = get_s3()
    try:
        s3.delete_object(Bucket=config.R2_BUCKET_NAME, Key=r2_key)
        return True
    except Exception as e:
        logger.error(f"Failed to delete {r2_key} from R2: {e}")
        return False


def delete_prefix(prefix: str) -> None:
    """Delete all objects with given prefix (e.g. projects/{project_id}/)."""
    if not config.has_r2():
        return
    s3 = get_s3()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=config.R2_BUCKET_NAME, Delete={"Objects": objects})
    except Exception as e:
        logger.error(f"Failed to delete prefix {prefix} from R2: {e}")


def get_storage_stats() -> dict:
    """Calculates total bytes and object count in the R2 bucket."""
    if not config.has_r2():
        return {
            "used_bytes": 0,
            "used_mb": 0.0,
            "used_gb": 0.0,
            "limit_bytes": 10 * 1024 * 1024 * 1024,
            "limit_gb": 10.0,
            "object_count": 0,
            "percentage": 0.0,
        }

    s3 = get_s3()
    total_bytes = 0
    total_objects = 0
    limit_bytes = 10 * 1024 * 1024 * 1024  # 10 GB Free Tier

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME):
            for obj in page.get("Contents", []):
                total_bytes += obj.get("Size", 0)
                total_objects += 1
    except Exception as e:
        logger.error(f"Failed to calculate R2 storage stats: {e}")

    pct = round((total_bytes / limit_bytes) * 100, 2)
    return {
        "used_bytes": total_bytes,
        "used_mb": round(total_bytes / (1024 * 1024), 2),
        "used_gb": round(total_bytes / (1024 * 1024 * 1024), 3),
        "limit_bytes": limit_bytes,
        "limit_gb": 10.0,
        "object_count": total_objects,
        "percentage": pct,
    }

