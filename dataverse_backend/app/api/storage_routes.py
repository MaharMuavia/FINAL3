"""Storage configuration status routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.config import settings
from ..services.supabase_client import supabase_client

router = APIRouter()


@router.get("/storage/status")
async def storage_status() -> dict[str, Any]:
    configured = supabase_client.configured
    return {
        "mode": "supabase" if configured else "local",
        "supabase_configured": configured,
        "dataset_bucket": settings.SUPABASE_DATASET_BUCKET,
        "report_bucket": settings.SUPABASE_REPORT_BUCKET,
    }
