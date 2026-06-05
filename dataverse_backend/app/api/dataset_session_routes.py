"""Top-level dataset sidebar routes for ChatGPT-style sessions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from ..api.schemas import AskRequest
from ..core.config import settings
from ..services.session_service import session_service


router = APIRouter()


@router.post("/datasets/upload")
async def upload_dataset_compat(
    file: UploadFile = File(...),
    dataverse_user: str | None = Header(default=None, alias="X-Dataverse-User"),
) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or "dataset.csv"
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")

    session = await session_service.create_session(title=f"Dataset: {filename}", user_id=dataverse_user)
    dataset = await session_service.upload_dataset(session["id"], filename, contents)
    column_names = [
        str(column.get("name", ""))
        for column in dataset.get("columns", [])
        if isinstance(column, dict)
    ]
    return {
        "dataset_id": dataset["id"],
        "session_id": dataset["session_id"],
        "filename": dataset["filename"],
        "row_count": dataset["row_count"],
        "column_count": dataset["column_count"],
        "columns": column_names,
        "profile": dataset.get("schema_profile") or {},
        "message": "Dataset uploaded and profiled successfully",
    }


@router.get("/datasets")
async def list_recent_datasets(
    dataverse_user: str | None = Header(default=None, alias="X-Dataverse-User"),
) -> list[dict[str, Any]]:
    return await session_service.list_datasets(user_id=dataverse_user)


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = await session_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get("/datasets/{dataset_id}/profile")
async def get_dataset_profile(dataset_id: str) -> dict[str, Any]:
    dataset = await session_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    columns = [
        str(column.get("name", ""))
        for column in dataset.get("columns", [])
        if isinstance(column, dict)
    ]
    return {
        "dataset_id": dataset["id"],
        "row_count": dataset.get("row_count", 0),
        "column_count": dataset.get("column_count", 0),
        "columns": columns,
        "profile": dataset.get("schema_profile") or {},
    }


@router.post("/datasets/{dataset_id}/ask")
async def ask_dataset(dataset_id: str, request: AskRequest) -> dict[str, Any]:
    dataset = await session_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        result = await session_service.analyze(
            str(dataset["session_id"]),
            dataset_id=dataset_id,
            user_prompt=request.prompt,
            run_xai=True,
            generate_report=False,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "answer": result.get("answer", ""),
        "summary": result.get("answer", ""),
        "tables": result.get("tables", []),
        "charts": result.get("charts", []),
        "recommendations": result.get("recommendations", []),
        "warnings": result.get("warnings", []),
        "next_questions": [],
    }


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = await session_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await session_service.delete_dataset(dataset_id)
    return {"dataset_id": dataset_id, "deleted": True}
