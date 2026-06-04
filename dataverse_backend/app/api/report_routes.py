"""Report generation and download routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from ..services.session_service import session_service


router = APIRouter()


@router.post("/sessions/{session_id}/reports/generate")
async def generate_report(session_id: str, dataset_id: str, title: str = "DataVerse Analysis Report") -> dict:
    try:
        result = await session_service.analyze(
            session_id,
            dataset_id=dataset_id,
            user_prompt=f"Generate final report: {title}",
            run_xai=True,
            generate_report=True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.get("report") or {}


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str, format: str = "pdf"):
    fmt = format.lower()
    if fmt not in {"pdf", "html"}:
        raise HTTPException(status_code=400, detail="format must be pdf or html")
    url, path = await session_service.get_report_download(report_id, fmt)
    if url:
        return RedirectResponse(url=url)
    if path:
        media_type = "application/pdf" if fmt == "pdf" else "text/html"
        return FileResponse(path, media_type=media_type, filename=f"dataverse-report.{fmt}")
    raise HTTPException(status_code=404, detail="Report not found")
