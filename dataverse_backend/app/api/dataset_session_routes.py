"""Top-level dataset sidebar routes for ChatGPT-style sessions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.session_service import session_service


router = APIRouter()


@router.get("/datasets")
async def list_recent_datasets() -> list[dict[str, Any]]:
    return await session_service.list_datasets()


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = await session_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict[str, Any]:
    await session_service.delete_dataset(dataset_id)
    return {"dataset_id": dataset_id, "deleted": True}
