"""Analytical routes for the AI Data Scientist MVP."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..api.schemas import AnalyzeQueryRequest
from ..agents.dataset_agent import DatasetAgent
from ..agents.analyst_agent import AnalystAgent
from ..services.session_store import (
    load_dataframe_for_session,
    load_semantic_map_for_session,
    persist_semantic_map_for_session,
)

router = APIRouter()
dataset_agent = DatasetAgent()
analyst_agent = AnalystAgent()


@router.post("/upload")
async def analyze_upload(
    file: UploadFile = File(...),
    target_column: str | None = Form(default=None),
    task_type: str | None = Form(default=None),
    run_predictions: bool = Form(default=True),
    run_xai: bool = Form(default=True),
    use_llm: bool = Form(default=True),
) -> dict[str, Any]:
    """Uploads a dataset and immediately runs a full analyst report (EDA, modeling, etc.)."""
    contents = await file.read()
    filename = file.filename or "upload.csv"

    # 1. DatasetAgent handles parsing, normalization, validation, and session store persistence
    session_id, df, _, _ = dataset_agent.parse_and_process(filename, contents)

    try:
        # 2. AnalystAgent executes the full analytical pipeline
        report = await analyst_agent.run_analysis(
            df=df,
            session_id=session_id,
            query="analyze uploaded dataset",
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            use_llm=use_llm,
            filename=filename,
        )
        report["session_id"] = session_id
        report["filename"] = filename

        # Persist the inferred semantic map for future query context
        if isinstance(report.get("semantic_map"), dict):
            persist_semantic_map_for_session(session_id, report["semantic_map"])

        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Automatic analysis failed: {exc}") from exc


@router.post("/query")
async def analyze_query(request: AnalyzeQueryRequest) -> dict[str, Any]:
    """Executes a query against an uploaded dataset, returning computations and answers."""
    # Load session state
    df, metadata = load_dataframe_for_session(request.session_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Session or dataset not found")

    semantic_map = load_semantic_map_for_session(request.session_id)

    # Use defaults if None
    run_predictions = True if request.run_predictions is None else request.run_predictions
    run_xai = True if request.run_xai is None else request.run_xai

    try:
        # AnalystAgent computes and answers query
        report = await analyst_agent.run_analysis(
            df=df,
            session_id=request.session_id,
            query=request.query,
            target_column=request.target_column,
            task_type=request.task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            use_llm=request.use_llm,
            semantic_map=semantic_map,
            filename=metadata.get("filename"),
        )
        report["session_id"] = request.session_id
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query analysis failed: {exc}") from exc
