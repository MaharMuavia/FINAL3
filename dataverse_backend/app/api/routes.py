"""Core legacy and session helper routes for the MVP."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..agents.dataset_agent import DatasetAgent
from ..services.session_store import delete_session, load_dataframe_for_session
from ..services.data_profiler import profile_dataframe
from ..services.data_quality import compute_data_quality

router = APIRouter()
dataset_agent = DatasetAgent()


@router.get("/health")
def health_check() -> dict[str, Any]:
    """Basic health check endpoint."""
    return {"status": "ok", "message": "Service is healthy"}


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    """Uploads, validates, parses, and profiles a dataset."""
    contents = await file.read()
    filename = file.filename or "upload.csv"

    # DatasetAgent handles validation, parsing, normalization, session store, and profiling
    session_id, df, profile, quality = dataset_agent.parse_and_process(filename, contents)

    return {
        "session_id": session_id,
        "filename": filename,
        "dataset_profile": profile,
        "data_quality": quality,
        "message": "Dataset uploaded and profiled. Use /api/analyze/upload for the full analyst report.",
    }


@router.get("/session/{session_id}")
def get_session_data(session_id: str) -> dict[str, Any]:
    """Retrieves dataset profile and metadata for an active session."""
    df, metadata = load_dataframe_for_session(session_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Session or dataset not found")

    profile = profile_dataframe(df)
    quality = compute_data_quality(df)

    return {
        "session_id": session_id,
        "filename": metadata.get("filename", "unknown"),
        "dataset_profile": profile,
        "data_quality": quality,
    }


@router.delete("/session/{session_id}")
def delete_session_data(session_id: str) -> dict[str, Any]:
    """Deletes an active session and cleans up resources."""
    success = delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}
