"""ChatGPT-style chat session, dataset, analysis, and message routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..api.schemas import ChatMessageCreate, ChatSessionCreate, ChatSessionUpdate, SessionAnalyzeRequest
from ..core.config import settings
from ..services.session_service import session_service


router = APIRouter()


@router.post("/sessions")
async def create_session(request: ChatSessionCreate) -> dict[str, Any]:
    return await session_service.create_session(title=request.title)


@router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return await session_service.list_sessions()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    try:
        return await session_service.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, request: ChatSessionUpdate) -> dict[str, Any]:
    payload = {key: value for key, value in request.model_dump(exclude_unset=True).items() if value is not None}
    updated = await session_service.update_session(session_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    await session_service.delete_session(session_id)
    return {"session_id": session_id, "deleted": True}


@router.post("/sessions/{session_id}/datasets/upload")
async def upload_dataset_to_session(
    session_id: str,
    file: UploadFile = File(...),
    auto_analyze: bool = Query(default=True),
    generate_report: bool = Query(default=True),
    run_xai: bool = Query(default=True),
) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or "dataset.csv"
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
    try:
        dataset = await session_service.upload_dataset(session_id, filename, contents)
        analysis = None
        if auto_analyze:
            analysis = await session_service.analyze(
                session_id,
                dataset_id=dataset["id"],
                user_prompt="Analyze this dataset",
                run_xai=run_xai,
                generate_report=generate_report,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid dataset upload: {exc}") from exc
    return {
        "dataset_id": dataset["id"],
        "session_id": session_id,
        "filename": dataset["filename"],
        "row_count": dataset["row_count"],
        "column_count": dataset["column_count"],
        "columns": dataset["columns"],
        "status": dataset["status"],
        "dataset": dataset,
        "analysis": analysis,
    }


@router.get("/sessions/{session_id}/datasets")
async def list_session_datasets(session_id: str) -> list[dict[str, Any]]:
    return await session_service.list_session_datasets(session_id)


@router.post("/sessions/{session_id}/analyze")
async def analyze_session(session_id: str, request: SessionAnalyzeRequest) -> dict[str, Any]:
    try:
        return await session_service.analyze(
            session_id,
            dataset_id=request.dataset_id,
            user_prompt=request.user_prompt,
            run_xai=request.run_xai,
            generate_report=request.generate_report,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/messages")
async def create_message(session_id: str, request: ChatMessageCreate) -> dict[str, Any]:
    try:
        return await session_service.chat_message(session_id, request.content, dataset_id=request.dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/agent-runs")
async def list_agent_runs(session_id: str) -> list[dict[str, Any]]:
    session = await session_service.get_session(session_id)
    return session.get("agent_runs", [])


@router.get("/sessions/{session_id}/reports")
async def list_session_reports(session_id: str) -> list[dict[str, Any]]:
    return await session_service.list_reports(session_id)
