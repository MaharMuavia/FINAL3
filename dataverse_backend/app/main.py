"""DataVerse AI — FastAPI Application Entry Point.

Simplified production-ready app with:
  - 4 dataset endpoints (upload, ask, profile, delete)
  - Health check
  - Safe error handling (no raw exception leaks)
  - CORS, GZip, request logging
"""
from __future__ import annotations

from contextlib import asynccontextmanager

<<<<<<< HEAD
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router as dataset_router
from .api.schemas import HealthResponse
=======
from .api import routes, auth_routes, stream, graph_routes, ai_routes, billing_routes, dashboard_routes
from .api import workspace_routes, dataset_routes, conversation_routes, analyze_routes
from .api import session_routes, dataset_session_routes, report_routes
from .api.websocket import ws_chat_endpoint
>>>>>>> 15b8a6d8 (new1)
from .core.config import settings
from .core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: create database tables on startup."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Create database tables
    try:
        from .db.base import get_engine
        from .db.models import Base
        engine = get_engine()
        if engine is not None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created/verified")
    except Exception:
        logger.warning("Database initialization skipped (non-critical)")

    yield

    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENABLE_OPENAPI_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_OPENAPI_DOCS else None,
    lifespan=lifespan,
)

<<<<<<< HEAD
# ── Middleware ──────────────────────────────────────────────
=======
# Include routers
app.include_router(auth_routes.router, prefix="/api/auth", tags=["authentication"])
app.include_router(workspace_routes.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(dataset_routes.router, prefix="/api/workspaces", tags=["datasets"])
app.include_router(conversation_routes.router, prefix="/api/workspaces", tags=["conversations"])
app.include_router(dashboard_routes.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(billing_routes.router, prefix="/api/billing", tags=["billing"])
app.include_router(ai_routes.router, prefix="/api/ai", tags=["ai"])
app.include_router(session_routes.router, prefix="/api", tags=["chat-sessions"])
app.include_router(dataset_session_routes.router, prefix="/api", tags=["chat-datasets"])
app.include_router(report_routes.router, prefix="/api", tags=["reports"])
app.include_router(analyze_routes.router, prefix="/api/analyze", tags=["analysis"])
app.include_router(routes.router, prefix="/api", tags=["legacy"])
app.include_router(stream.router, prefix="/api/stream", tags=["streaming"])
app.include_router(graph_routes.router, prefix="/api/stream/graph", tags=["langgraph"])
>>>>>>> 15b8a6d8 (new1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)



# ── Global exception handler — never leak raw exceptions ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler. Never returns str(exc) to the client."""
    logger.exception("Unhandled exception", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routes ──────────────────────────────────────────────────

app.include_router(dataset_router, prefix="/api", tags=["datasets"])


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live():
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready():
    """Readiness check — verifies DB connectivity."""
    status = "ok"
    try:
        from .db.base import get_engine
        engine = get_engine()
        if engine is not None:
            from sqlalchemy import text
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        status = "degraded"

    return HealthResponse(
        status=status,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )
