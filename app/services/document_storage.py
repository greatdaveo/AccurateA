import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, BinaryIO

# S3 support is optional — only imported if needed
try:
    import boto3
    from botocore.config import Config as BotoConfig
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


# Allowed file types and max size
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class StorageError(Exception):
    """Raised when a storage operation fails."""
    pass


class DocumentStorage:
    """
    Unified storage interface.

    Usage:
        storage = DocumentStorage()
        key, url = storage.upload(file, filename, company_id)
        url = storage.get_url(key)
        storage.delete(key)
    """

    def __init__(self):
        self.backend = os.getenv("STORAGE_BACKEND", "local").lower()

        if self.backend == "s3":
            if not HAS_BOTO3:
                raise StorageError(
                    "boto3 is required for S3 storage. Install with: pip install boto3"
                )
            self.bucket = os.getenv("S3_BUCKET_NAME", "accountea-documents")
            self.s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                region_name=os.getenv("S3_REGION", "auto"),
                config=BotoConfig(signature_version="s3v4"),
            )
        else:
            self.local_path = Path(
                os.getenv("STORAGE_LOCAL_PATH", "./uploads")
            )
            self.local_path.mkdir(parents=True, exist_ok=True)

    def validate_file(self, content_type: str, file_size: int, filename: str):
        """Validate file type and size before upload."""
        if content_type not in ALLOWED_TYPES:
            raise StorageError(
                f"File type '{content_type}' not allowed. "
                f"Allowed: {', '.join(ALLOWED_TYPES.values())}"
            )

        if file_size > MAX_FILE_SIZE:
            raise StorageError(
                f"File too large ({file_size / 1024 / 1024:.1f}MB). "
                f"Maximum: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            )

    def upload(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        company_id: str,
    ) -> tuple[str, str]:
        """
        Upload a file.

        Returns:
            (storage_key, file_url) tuple
        """
        # Generate a unique key: company_id/YYYY/MM/uuid_filename
        ext = ALLOWED_TYPES.get(content_type, "")
        now = datetime.utcnow()
        unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"
        key = f"{company_id}/{now.year}/{now.month:02d}/{unique_name}"

        if self.backend == "s3":
            return self._upload_s3(file, key, content_type)
        else:
            return self._upload_local(file, key)

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get a download URL for a stored file."""
        if self.backend == "s3":
            return self._get_url_s3(key, expires_in)
        else:
            return self._get_url_local(key)

    def delete(self, key: str):
        """Delete a file from storage."""
        if self.backend == "s3":
            self._delete_s3(key)
        else:
            self._delete_local(key)

    # LOCAL BACKEND
    def _upload_local(self, file: BinaryIO, key: str) -> tuple[str, str]:
        file_path = self.local_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file, f)

        url = f"/uploads/{key}"
        return key, url

    def _get_url_local(self, key: str) -> str:
        return f"/uploads/{key}"

    def _delete_local(self, key: str):
        file_path = self.local_path / key
        if file_path.exists():
            file_path.unlink()

    # S3 / R2 BACKEND
    def _upload_s3(self, file: BinaryIO, key: str, content_type: str) -> tuple[str, str]:
        try:
            self.s3.upload_fileobj(
                file,
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
            url = self._get_url_s3(key)
            return key, url
        except Exception as e:
            raise StorageError(f"S3 upload failed: {e}")

    def _get_url_s3(self, key: str, expires_in: int = 3600) -> str:
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            raise StorageError(f"Failed to generate URL: {e}")

    def _delete_s3(self, key: str):
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            raise StorageError(f"S3 delete failed: {e}")


# Singleton for reuse
_storage: Optional[DocumentStorage] = None

def get_storage() -> DocumentStorage:
    global _storage
    if _storage is None:
        _storage = DocumentStorage()
    return _storage
