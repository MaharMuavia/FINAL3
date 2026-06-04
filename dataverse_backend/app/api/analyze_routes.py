"""Automatic AI data analyst endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..api.schemas import AnalyzeQueryRequest
from ..api.upload_parsing import parse_uploaded_dataframe
from ..core.config import settings
from ..core.logger import logger
from ..services.analysis_pipeline import AnalysisPipeline
from ..services.session_store import (
    create_session_id,
    load_dataframe_for_session,
    load_semantic_map_for_session,
    persist_dataframe_for_session,
    persist_semantic_map_for_session,
)


router = APIRouter()


@router.post("/upload")
async def analyze_upload(
    file: UploadFile = File(...),
    target_column: str | None = Form(default=None),
    task_type: str | None = Form(default=None),
    run_predictions: bool = Form(default=True),
    run_xai: bool = Form(default=True),
    use_llm: bool = Form(default=True),
    provider: str | None = Form(default=None),
) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or "upload.csv"
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
    if task_type and task_type not in {"regression", "classification"}:
        raise HTTPException(status_code=400, detail="task_type must be regression or classification")

    try:
        df = parse_uploaded_dataframe(filename, contents)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file upload: {exc}") from exc

    session_id = create_session_id()
    try:
        persist_dataframe_for_session(session_id, df, filename=filename)
        report = await AnalysisPipeline().run_full_analysis_async(
            df,
            query="analyze uploaded dataset",
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            session_id=session_id,
            filename=filename,
            use_llm=use_llm,
            provider=provider,
        )
        report["session_id"] = session_id
        report["filename"] = filename
        if isinstance(report.get("semantic_map"), dict):
            persist_semantic_map_for_session(session_id, report["semantic_map"])
        return report
    except Exception as exc:
        logger.exception("Automatic upload analysis failed")
        raise HTTPException(status_code=500, detail="Automatic analysis failed") from exc


@router.post("/query")
async def analyze_query(request: AnalyzeQueryRequest) -> dict[str, Any]:
    df, metadata = load_dataframe_for_session(request.session_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Session or dataset not found")
    semantic_map = load_semantic_map_for_session(request.session_id)
    try:
        report = await AnalysisPipeline().run_full_analysis_async(
            df,
            query=request.query,
            target_column=request.target_column,
            task_type=request.task_type,
            run_predictions=True if request.run_predictions is None else request.run_predictions,
            run_xai=True if request.run_xai is None else request.run_xai,
            session_id=request.session_id,
            filename=metadata.get("filename"),
            use_llm=request.use_llm,
            provider=request.provider,
            semantic_map=semantic_map,
        )
        report["session_id"] = request.session_id
        return report
    except Exception as exc:
        logger.exception("Query-specific analysis failed")
        raise HTTPException(status_code=500, detail="Query analysis failed") from exc
