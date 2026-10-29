"""
Application configuration for PDF Workbench.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Set

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
# Bounded below Google Cloud Run's 32 MiB HTTP/1 payload limit
MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024  # 30 MiB hard limit

COMPROMISED_FALLBACK_KEYS: Set[str] = {
    "vellakshya_secure_storage_hmac_secret_2026",
    "vellakshya_canonical_manifest_secret_key_2026_ed25519_prod",
}


def is_production() -> bool:
    env = os.environ.get("ENVIRONMENT", os.environ.get("ENV", "development")).lower()
    return env in ("production", "prod")


_CACHED_STORAGE_KEY: bytes | None = None
_CACHED_MANIFEST_KEY: bytes | None = None


def get_storage_signing_key() -> bytes:
    global _CACHED_STORAGE_KEY
    key_str = os.environ.get("STORAGE_SIGNING_KEY")
    if is_production():
        if not key_str:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: STORAGE_SIGNING_KEY must be configured in production."
            )
        if key_str in COMPROMISED_FALLBACK_KEYS:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: Compromised fallback STORAGE_SIGNING_KEY cannot be used in production."
            )
        return key_str.encode("utf-8")

    if key_str:
        if key_str in COMPROMISED_FALLBACK_KEYS:
            raise ValueError(
                "Compromised literal STORAGE_SIGNING_KEY rejected. Set a fresh secret key."
            )
        return key_str.encode("utf-8")

    # In dev/test: generate a fresh high-entropy random key per process lifetime
    if _CACHED_STORAGE_KEY is None:
        _CACHED_STORAGE_KEY = secrets.token_bytes(32)
    return _CACHED_STORAGE_KEY


def get_manifest_signing_key() -> bytes:
    global _CACHED_MANIFEST_KEY
    key_str = os.environ.get("MANIFEST_SIGNING_KEY")
    if is_production():
        if not key_str:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: MANIFEST_SIGNING_KEY must be configured in production."
            )
        if key_str in COMPROMISED_FALLBACK_KEYS:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: Compromised fallback MANIFEST_SIGNING_KEY cannot be used in production."
            )
        return key_str.encode("utf-8")[:32].ljust(32, b"0")

    if key_str:
        if key_str in COMPROMISED_FALLBACK_KEYS:
            raise ValueError(
                "Compromised literal MANIFEST_SIGNING_KEY rejected. Set a fresh secret key."
            )
        return key_str.encode("utf-8")[:32].ljust(32, b"0")

    if _CACHED_MANIFEST_KEY is None:
        _CACHED_MANIFEST_KEY = secrets.token_bytes(32)
    return _CACHED_MANIFEST_KEY


@dataclass(frozen=True)
class AppConfig:
    title: str = "Vellakshya PDF Workstation"
    version: str = "2.0.0"
    max_upload_size: int = MAX_UPLOAD_SIZE_BYTES
    allowed_extensions: tuple = (".pdf", ".png", ".jpg", ".jpeg")

    @property
    def is_prod(self) -> bool:
        return is_production()

    @property
    def storage_signing_key(self) -> bytes:
        return get_storage_signing_key()

    @property
    def manifest_signing_key(self) -> bytes:
        return get_manifest_signing_key()


config = AppConfig()
