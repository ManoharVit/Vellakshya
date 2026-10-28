"""
Vellakshya Object Storage Abstraction Layer.
Implements S3-compatible storage semantics and secure presigned URL generation.
Separates binary document storage from relational metadata.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "object_store"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

SECRET_STORAGE_KEY = os.environ.get(
    "STORAGE_SIGNING_KEY", "vellakshya_secure_storage_hmac_secret_2026"
)


class ObjectNotFoundError(Exception):
    """Raised when an object key does not exist in storage."""

    pass


class StorageService:
    """
    Manages immutable binary document storage with cryptographic digest computation
    and time-limited presigned access URLs.
    """

    def __init__(self, root_dir: Optional[Path] = None, signing_secret: Optional[str] = None):
        self.root_dir = root_dir or STORAGE_ROOT
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.signing_secret = (signing_secret or SECRET_STORAGE_KEY).encode("utf-8")

    def _resolve_path(self, key: str) -> Path:
        # Prevent directory traversal attacks
        clean_key = Path(key).as_posix().lstrip("/")
        if ".." in clean_key:
            raise ValueError(f"Path traversal detected in storage key: {key}")
        full_path = self.root_dir / clean_key
        return full_path

    def compute_sha256(self, data: bytes) -> str:
        """Computes NIST SHA-256 hex digest over bytes."""
        return hashlib.sha256(data).hexdigest()

    def store_object(
        self, key: str, data: bytes, content_type: str = "application/pdf"
    ) -> tuple[str, str, int]:
        """
        Persists immutable binary object and returns (key, sha256_digest, byte_size).
        """
        dest_path = self._resolve_path(key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)

        digest = self.compute_sha256(data)
        size = len(data)

        # Write metadata descriptor alongside object
        meta_path = dest_path.with_suffix(dest_path.suffix + ".meta")
        meta = {
            "key": key,
            "sha256": digest,
            "byte_size": size,
            "content_type": content_type,
            "stored_at": time.time(),
        }
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        return key, digest, size

    def get_object(self, key: str) -> bytes:
        """Retrieves raw object bytes."""
        path = self._resolve_path(key)
        if not path.is_file():
            raise ObjectNotFoundError(f"Object with key '{key}' not found.")
        return path.read_bytes()

    def object_exists(self, key: str) -> bool:
        """Checks if key exists."""
        try:
            return self._resolve_path(key).is_file()
        except ValueError:
            return False

    def delete_object(self, key: str) -> bool:
        """Deletes object and metadata if present."""
        path = self._resolve_path(key)
        if path.is_file():
            path.unlink()
            meta = path.with_suffix(path.suffix + ".meta")
            if meta.is_file():
                meta.unlink()
            return True
        return False

    def generate_presigned_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
        method: str = "GET",
    ) -> str:
        """
        Generates a secure, time-limited presigned URL with cryptographic HMAC-SHA256 signature.
        """
        expires_at = int(time.time()) + expires_in_seconds
        payload = f"{method}:{key}:{expires_at}"
        signature = hmac.new(
            self.signing_secret, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Token structure: base64(json)
        token_data = {
            "key": key,
            "exp": expires_at,
            "method": method.upper(),
            "sig": signature,
        }
        token_str = base64.urlsafe_b64encode(json.dumps(token_data).encode("utf-8")).decode("utf-8")
        return f"/api/v2/storage/presigned?token={token_str}"

    def validate_presigned_token(self, token: str) -> tuple[str, str]:
        """
        Validates token integrity and expiration. Returns (key, method).
        Raises ValueError if expired, malformed, or tampered.
        """
        try:
            raw_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            raise ValueError("Malformed or invalid presigned token structure.")

        key = data.get("key")
        exp = data.get("exp")
        method = data.get("method")
        provided_sig = data.get("sig")

        if not all([key, exp, method, provided_sig]):
            raise ValueError("Missing essential claims in presigned token.")

        if time.time() > float(exp):
            raise ValueError("Presigned URL has expired.")

        expected_payload = f"{method}:{key}:{exp}"
        expected_sig = hmac.new(
            self.signing_secret, expected_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(provided_sig, expected_sig):
            raise ValueError("Presigned token cryptographic signature is invalid or tampered.")

        return key, method


# Global Singleton Storage Instance
storage_instance = StorageService()
