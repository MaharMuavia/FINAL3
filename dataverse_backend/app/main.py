"""DataVerse AI — FastAPI Application Entry Point (Clean MVP)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .api.analyze_routes import router as analyze_router
from .api.dataset_session_routes import router as dataset_session_router
from .api.report_routes import router as report_router
from .api.routes import router as core_router
from .api.session_routes import router as session_router
from .api.storage_routes import router as storage_router
from .core.config import settings
from .core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: simple startup/shutdown logs without DB dependencies."""
    logger.info(f"Starting {settings.APP_NAME} MVP v{settings.APP_VERSION}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENABLE_OPENAPI_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_OPENAPI_DOCS else None,
    lifespan=lifespan,
)

# ── Middleware ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/health/live")
def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


# ── Global Exception Handler ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global catch-all exception handler with environment-aware error shapes."""
    logger.exception("Unhandled exception occurred", extra={"path": request.url.path})

    status_code = 500
    message = str(exc)

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        message = exc.detail

    is_dev = settings.ENVIRONMENT == "development"

    if is_dev:
        # Development mode: return rich exception details and a user-friendly fix suggestion
        fix_suggestion = "Please review the request parameters or server console logs for debugging."
        
        # Customize suggestions based on common error types or patterns
        exc_str = str(exc).lower()
        if "target_column" in exc_str or "target" in exc_str:
            fix_suggestion = "Check that target_column is spelled correctly and matches a column in the dataset."
        elif "rows" in exc_str or "empty" in exc_str:
            fix_suggestion = "Upload a non-empty CSV/Excel file containing structured rows."
        elif isinstance(exc, FileNotFoundError) or "not found" in exc_str:
            fix_suggestion = "Verify that the session_id is valid and has not expired or been deleted."
        elif "format" in exc_str or "encoding" in exc_str:
            fix_suggestion = "Ensure the uploaded file is a valid CSV or Excel file (UTF-8 encoding is recommended)."

        return JSONResponse(
            status_code=status_code,
            content={
                "error_name": exc.__class__.__name__,
                "exception_type": type(exc).__name__,
                "message": message,
                "fix_suggestion": fix_suggestion,
            },
        )
    else:
        # Production mode: hide internal tracebacks and return generic message
        return JSONResponse(
            status_code=status_code,
            content={"detail": message if isinstance(exc, HTTPException) else "An unexpected error occurred. Please try again."},
        )


# ── Include Routers ──────────────────────────────────────────
# /api/health, /api/upload, /api/session/{session_id} (GET/DELETE)
app.include_router(core_router, prefix="/api", tags=["core"])

# ChatGPT-style session, dataset, agent-run, report, and storage routes.
app.include_router(session_router, prefix="/api", tags=["chat-sessions"])
app.include_router(dataset_session_router, prefix="/api", tags=["chat-datasets"])
app.include_router(report_router, prefix="/api", tags=["reports"])
app.include_router(storage_router, prefix="/api", tags=["storage"])

# /api/analyze/upload, /api/analyze/query
app.include_router(analyze_router, prefix="/api/analyze", tags=["analysis"])
