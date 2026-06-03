"""Local file storage — simplified.

Stores uploaded files as parquet in a local directory.
MinIO/S3 support removed for MVP simplicity.
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import settings


def get_upload_dir() -> Path:
    """Return the upload directory, creating it if needed."""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_file_path(filename: str) -> str:
    """Return the absolute file path for a given filename in the upload dir."""
    return str(get_upload_dir() / filename)


def delete_file(filepath: str) -> bool:
    """Delete a file if it exists. Returns True if deleted."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
    except OSError:
        pass
    return False
