"""
Application configuration for PDF Workbench.
"""

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
# Bounded below Google Cloud Run's 32 MiB HTTP/1 payload limit
MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024  # 30 MiB hard limit


@dataclass(frozen=True)
class AppConfig:
    title: str = "Vellakshya PDF Workstation"
    version: str = "2.0.0"
    max_upload_size: int = MAX_UPLOAD_SIZE_BYTES
    allowed_extensions: tuple = (".pdf", ".png", ".jpg", ".jpeg")


config = AppConfig()
