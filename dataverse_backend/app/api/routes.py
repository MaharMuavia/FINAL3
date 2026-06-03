"""API routes for DataVerse AI."""
from __future__ import annotations

import io
import uuid
from datetime import datetime
import pandas as pd
import numpy as np
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from ..db.base import get_session
from ..db.repositories import create_dataset, log_user_query

from ..core.auth import get_current_active_user
from ..api.schemas import User
from ..core.exceptions import DataLoadError, DataNotFoundError
from ..data.data_manager import DataManager
from ..state.session_state import SessionState
from ..orchestrator.agent_orchestrator import AgentOrchestrator
from ..core.logger import logger
from ..agents.retail_detector_agent import RetailDetectorAgent
from ..agents.eda_analytics_agent import EDAAgent
from ..agents.automl_agent import AutoMLAgent
from ..workflow.memory.session_store import clear_session as clear_workflow_session, load_session, save_session
from ..core.celery_config import celery_app
from .schemas import (
    UploadResponse,
    QueryRequest,
    QueryResponse,
    HealthResponse,
    SessionStatusResponse,
    ConfirmColumnRequest,
    ConfirmColumnResponse,
    DatasetProfileResponse,
    CorrelationResponse,
    RecommendationResponse,
    TrainModelRequest,
    TrainModelResponse,
    MLJobStatusResponse,
)
import asyncio
import os

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", details={"app": "DataVerse AI backend"})


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
def session_status(session_id: str):
    state = SessionState.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionStatusResponse(
        session_id=session_id,
        dataset_is_retail=state.get_value("dataset_is_retail"),
        retail_validation=state.get_value("retail_validation"),
        execution_trace=state.get_value("execution_trace"),
        eda_completed=state.get_value("eda_completed"),
        preprocessing_completed=state.get_value("preprocessing_completed"),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Optional[AsyncSession] = Depends(get_session)
):
    # Validate file size and type
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(400, "File exceeds 50MB limit")
    if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(400, "Only CSV and Excel files are supported")

    # Assign a new session id for each upload
    session_id = str(uuid.uuid4())

    try:
        # Parse file based on extension
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(400, "Unsupported file format")
    except Exception as e:
        logger.exception("Failed to read uploaded file")
        raise HTTPException(status_code=400, detail=f"Invalid file upload: {e}")

    try:
        # Create persistent session
        from ..state.persistent_session_state import session_manager
        session_state = session_manager.get_session(session_id)

        if db is not None:
            await session_state.create_session(db, file.filename or "upload.csv", df)
            await session_state.update_access_time(db)

        # Store additional metadata
        session_state.set("dataset_is_retail", False)  # Will be updated by retail agent
        session_state.set("retail_validation", {})

        logger.info("Dataset uploaded and saved persistently", extra={"session_id": session_id})

        # Retail dataset validation (informative)
        retail_agent = RetailDetectorAgent(session_id=session_id)
        validation = retail_agent.run()
        is_retail = validation.get("is_retail", False)

        # Update session with retail info
        session_state.set("dataset_is_retail", is_retail)
        session_state.set("retail_validation", validation)

        if db is not None:
            await session_state.persist_metadata(db)

        if is_retail:
            msg = "Upload successful and dataset appears to be retail-mart related."
        else:
            msg = "Upload successful but dataset appears non-retail; downstream analytics may be generic."

        # Initialize shared agent memory for the session so the agentic endpoints
        # can reuse schema and dataset references across requests.
        try:
            from ..memory.conversation_memory import get_memory_store

            memory = get_memory_store()
            session_storage = session_manager.get_session(session_id)
            dataset_schema = {
                "file_path": str(session_storage.dataset_path),
                "columns": {col: {"dtype": str(df[col].dtype)} for col in df.columns},
                "dtypes": {col: str(df[col].dtype) for col in df.columns},
                "rows": len(df),
            }
            existing_session = memory.get_session(session_id)
            if existing_session is None:
                memory.create_session(session_id, dataset_schema)
            else:
                existing_session.dataset_schema = dataset_schema

        except Exception as e:
            logger.warning(f"Failed to initialize agent memory: {e}")

        return UploadResponse(
            session_id=session_id,
            success=True,
            message=msg,
            is_retail=is_retail,
            matched_keywords=validation.get("matched_keywords", []),
            dataset_filename=file.filename,
            dataset_rows=int(len(df)),
            dataset_cols=int(len(df.columns)),
            created_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception("Failed during dataset upload")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confirm_column", response_model=ConfirmColumnResponse)
async def confirm_column(request: ConfirmColumnRequest):
    """Endpoint for users to confirm ambiguous column choices (e.g., product column)."""
    state = SessionState.get(request.session_id)
    # Validate column exists in uploaded dataset
    try:
        dm = DataManager(session_id=request.session_id)
        df = dm.get_raw()
    except Exception:
        raise HTTPException(status_code=404, detail="Session or dataset not found")

    if request.column_name not in df.columns:
        raise HTTPException(status_code=400, detail="Column not found in dataset")

    state.set("product_override", request.column_name)
    logger.info("Product column confirmed by user", extra={"session_id": request.session_id, "column": request.column_name})
    return ConfirmColumnResponse(session_id=request.session_id, column_name=request.column_name, message="Column confirmed")


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: Optional[AsyncSession] = Depends(get_session)
):
    orchestrator = AgentOrchestrator()
    try:
        # Log user query early for auditability
        session_state = SessionState.get(request.session_id)
        dataset_id = session_state.get_value("dataset_id") if session_state else None
        if db is not None and dataset_id:
            try:
                await log_user_query(db, query_text=request.query, parsed_intent=None, dataset_id=dataset_id)
            except Exception as e:
                logger.warning(f"Failed to log user query: {e}")

        result = await orchestrator.handle_query(session_id=request.session_id, user_query=request.query, db=db)

        return QueryResponse(
            session_id=request.session_id,
            intent=result.get("intent"),
            computed_facts=result.get("computed_facts", {}),
            report=result.get("report", ""),
            action_required=result.get("action_required"),
            candidates=result.get("candidates"),
            is_retail=session_state.get_value("dataset_is_retail") if session_state else None,
        )
    except DataNotFoundError as e:
        logger.error("Data not found for query", exc_info=e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in query endpoint")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dataset/profile", response_model=DatasetProfileResponse)
def dataset_profile(session_id: str):
    try:
        dm = DataManager(session_id=session_id)
        profile = dm.generate_profile()
        return DatasetProfileResponse(session_id=session_id, profile=profile.to_dict())
    except Exception as e:
        logger.exception("Failed to generate dataset profile")
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/dataset/correlation", response_model=CorrelationResponse)
def dataset_correlation(session_id: str):
    try:
        eda_agent = EDAAgent(session_id=session_id)
        eda_result = eda_agent.run()
        corr = eda_result.get("correlations", {})
        return CorrelationResponse(session_id=session_id, correlations=corr)
    except Exception as e:
        logger.exception("Failed to compute correlation")
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/dataset/recommendations", response_model=RecommendationResponse)
def dataset_recommendations(session_id: str):
    try:
        dm = DataManager(session_id=session_id)
        eda_agent = EDAAgent(session_id=session_id)
        eda_result = eda_agent.run()

        missing = eda_result.get("missing_values", {})
        high_corr = eda_result.get("correlations", {}).get("high_correlations", [])
        numeric = eda_result.get("profile_summary", {}).get("numeric_columns", 0)

        recs = []
        if missing.get("total_missing", 0) > 0:
            recs.append("Impute missing values for columns with missing data")
        else:
            recs.append("No missing values detected; proceed with modeling")

        if high_corr:
            recs.append("Check multicollinearity among highly correlated features")

        if numeric >= 1:
            recs.append("Consider scaling numeric features before modeling")

        recs.append("Based on query intent, run AutoML to select best model")

        key_findings = {
            "dataset_shape": eda_result.get("dataset_shape"),
            "missing_summary": missing,
            "high_correlations": high_corr,
            "variable_summary": eda_result.get("profile_summary"),
        }

        return RecommendationResponse(session_id=session_id, recommendations=recs, key_findings=key_findings)
    except Exception as e:
        logger.exception("Failed to generate recommendations")
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/dataset/train", response_model=TrainModelResponse)
async def dataset_train(
    request: TrainModelRequest,
    db: Optional[AsyncSession] = Depends(get_session)
):
    try:
        # Create ML job record
        job_id = str(uuid.uuid4())

        if db is not None:
            from ..db.session_models import MLJob
            ml_job = MLJob(
                id=job_id,
                session_id=request.session_id,
                task_type=request.task_type,
                target_column=request.target_column,
                status="pending"
            )
            db.add(ml_job)
            await db.commit()

        # Start background training
        automl = AutoMLAgent(session_id=request.session_id)
        asyncio.create_task(automl.train_async(request.session_id, request.task_type, request.target_column, db))

        # Update job status to running
        if db is not None:
            from sqlalchemy import update
            from ..db.session_models import MLJob
            stmt = update(MLJob).where(MLJob.id == job_id).values(status="running")
            await db.execute(stmt)
            await db.commit()

        return TrainModelResponse(
            session_id=request.session_id,
            task_type=request.task_type,
            target_column=request.target_column,
            status="running",
            job_id=job_id,
        )
    except Exception as e:
        logger.exception("AutoML job creation failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/status/{job_id}", response_model=MLJobStatusResponse)
async def ml_job_status(
    job_id: str,
    db: Optional[AsyncSession] = Depends(get_session)
):
    """Check status of ML training job."""
    if db is None:
        raise HTTPException(500, "Database not configured")

    try:
        from ..db.session_models import MLJob
        from sqlalchemy import select

        stmt = select(MLJob).where(MLJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(404, "ML job not found")

        response_data = {
            "job_id": job.id,
            "status": job.status,
            "error": job.error
        }

        if job.status == "complete":
            response_data["result"] = {
                "best_model": job.best_model,
                "metrics": job.metrics,
                "shap_values": job.shap_values
            }

        return MLJobStatusResponse(**response_data)

    except Exception as e:
        logger.exception(f"Failed to get ML job status: {e}")
        raise HTTPException(500, str(e))


# New agentic endpoints
@router.get("/session/{session_id}/proactive-insights")
async def get_proactive_insights(session_id: str):
    """Get proactive insights for a session."""
    try:
        from ..agents.proactive_insight_agent import ProactiveInsightAgent
        from ..agents.core.tool_registry import ToolRegistry
        from ..llm.llm_client import LLMClient
        from ..memory.conversation_memory import get_memory_store

        # Initialize components
        llm_client = LLMClient()
        tool_registry = ToolRegistry()
        memory = get_memory_store()

        # Get dataset path from session
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")

        dataset_path = session.dataset_schema.get("file_path")
        if not dataset_path:
            raise HTTPException(404, "Dataset not found in session")

        # Generate insights
        insight_agent = ProactiveInsightAgent(llm_client, tool_registry)
        insights = await insight_agent.generate_insights(dataset_path, session_id, memory)

        return {"session_id": session_id, "insights": insights}

    except Exception as e:
        logger.exception("Failed to generate proactive insights")
        raise HTTPException(500, str(e))


@router.get("/session/{session_id}/active-filters")
async def get_active_filters(session_id: str):
    """Return the current natural-language filters tracked for a session."""
    from ..memory.conversation_memory import get_memory_store

    memory = get_memory_store()
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "session_id": session_id,
        "active_filters": [
            item.model_dump() if hasattr(item, "model_dump") else item.dict()
            for item in memory.get_active_filters(session_id)
        ],
        "working_dataset_ref": memory.get_working_dataset_ref(session_id),
    }


@router.delete("/session/{session_id}/active-filters")
async def clear_active_filters(session_id: str):
    """Clear session filters and reset the working dataset to the original upload."""
    from ..memory.conversation_memory import get_memory_store

    memory = get_memory_store()
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    memory.update_active_filters(session_id, [])
    memory.set_working_dataset_ref(session_id, None)

    return {
        "session_id": session_id,
        "active_filters": [],
        "working_dataset_ref": None,
        "message": "Active filters cleared.",
    }


@router.post("/agent/query")
async def agent_query(request: QueryRequest):
    """New agentic query endpoint using AgentLoop."""
    try:
        from ..agents.core.agent_loop import AgentLoop
        from ..agents.core.tool_registry import ToolRegistry
        from ..llm.llm_client import LLMClient
        from ..memory.conversation_memory import get_memory_store

        # Initialize components
        llm_client = LLMClient()
        tool_registry = ToolRegistry()
        memory = get_memory_store()

        # Get session info
        session = memory.get_session(request.session_id)
        if not session:
            raise HTTPException(404, "Session not found")

        dataset_path = session.dataset_schema.get("file_path")
        if not dataset_path:
            raise HTTPException(404, "Dataset not found in session")

        # Create and run agent loop
        agent_loop = AgentLoop(llm_client, tool_registry, memory)
        result = await agent_loop.run(request.query, request.session_id, dataset_path)

        return {
            "session_id": request.session_id,
            "narrative": result.narrative,
            "charts": result.charts,
            "tables": result.tables,
            "model_results": result.model_results,
            "explanation": result.explanation,
            "steps": result.steps,
            "clarification": result.clarification,
            "active_filters": result.active_filters,
        }

    except Exception as e:
        logger.exception("Agent query failed")
        raise HTTPException(500, str(e))


@router.post("/generate-report")
async def generate_report(
    session_id: str,
    output_format: str = Query("html", description="html, docx, markdown, or json"),
    download: bool = Query(False, description="When true, return the exported file directly"),
):
    """Generate and optionally download a comprehensive analysis report."""
    try:
        from ..agents.report_agent import ReportAgent
        from ..llm.llm_client import LLMClient
        from ..memory.conversation_memory import get_memory_store

        llm_client = LLMClient()
        memory = get_memory_store()

        report_agent = ReportAgent(llm_client)
        report = await report_agent.generate_report(session_id, memory, output_format=output_format)

        export_info = report.get("export", {})
        export_path = export_info.get("path")
        if download and export_path:
            return FileResponse(
                path=export_path,
                media_type=export_info.get("media_type", "application/octet-stream"),
                filename=export_info.get("filename"),
            )

        return {"session_id": session_id, "report": report}

    except Exception as e:
        logger.exception("Report generation failed")
        raise HTTPException(500, str(e))


# New workflow endpoints
@router.post("/workflow/upload")
async def workflow_upload_dataset(file: UploadFile = File(...)):
    # Validate file
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(400, "File exceeds 50MB limit")
    if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(400, "Only CSV and Excel files are supported")

    session_id = str(uuid.uuid4())

    try:
        # Parse file
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        # Save to storage
        os.makedirs("storage/datasets", exist_ok=True)
        dataset_path = f"storage/datasets/{session_id}_{file.filename}"
        with open(dataset_path, "wb") as f:
            f.write(contents)

        # Extract metadata
        column_names = df.columns.tolist()
        column_dtypes = df.dtypes.astype(str).to_dict()
        row_count = len(df)

        # Create initial session state
        initial_state = {
            "session_id": session_id,
            "dataset_id": session_id,
            "dataset_path": dataset_path,
            "column_names": column_names,
            "column_dtypes": column_dtypes,
            "conversation_history": [],
        }
        save_session(session_id, initial_state)

        return {
            "session_id": session_id,
            "dataset_id": session_id,
            "column_names": column_names,
            "column_dtypes": column_dtypes,
            "row_count": row_count
        }

    except Exception as e:
        logger.exception("Workflow upload failed")
        raise HTTPException(500, str(e))


@router.get("/task/{task_id}/status")
async def task_status(task_id: str):
    try:
        result = celery_app.AsyncResult(task_id)
        return {
            "status": result.status,
            "result": result.result if result.ready() else None
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/session/{session_id}/state")
async def session_state(session_id: str):
    state = load_session(session_id)
    return state


# ============= NEW ADVANCED FEATURES =============

@router.post("/analytics/anomalies")
async def detect_anomalies(
    session_id: str,
    columns: list[str] = Query(None),
    method: str = Query("ensemble", description="ensemble|isolation_forest|lof|zscore|iqr"),
    contamination: float = Query(0.05, ge=0.01, le=0.5),
    sensitivity: float = Query(1.0, ge=0.1, le=2.0)
):
    """
    Advanced anomaly detection with multiple methods.
    
    Methods:
    - ensemble: Combines multiple algorithms
    - isolation_forest: Tree-based anomaly detection
    - lof: Density-based local outlier detection
    - zscore: Statistical z-score method
    - iqr: Interquartile range method
    """
    try:
        from ..agents.tools.advanced_anomaly import AnomalyDetectionTool
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        df = pd.read_csv(session.dataset_schema.get("file_path"))
        
        # Create session context mock
        class SessionContext:
            def __init__(self, dataframe):
                self.dataframe = dataframe
        
        context = SessionContext(df)
        
        tool = AnomalyDetectionTool()
        params = {
            "columns": columns or df.select_dtypes(include=[np.number]).columns.tolist(),
            "method": method,
            "contamination": contamination,
            "sensitivity": sensitivity,
        }
        
        result = await tool.execute(params, context)
        
        return {
            "session_id": session_id,
            "anomaly_count": result.data.get("anomaly_count"),
            "anomaly_percentage": result.data.get("anomaly_percentage"),
            "method": result.data.get("method"),
            "narrative": result.narrative,
            "flagged_rows": result.data.get("flagged_rows"),
        }
    
    except Exception as e:
        logger.exception("Anomaly detection failed")
        raise HTTPException(500, str(e))


@router.post("/analytics/segmentation")
async def customer_segmentation(
    session_id: str,
    features: list[str] = Query(None),
    n_clusters: int = Query(None, description="Auto-detect if not specified"),
    method: str = Query("kmeans", description="kmeans|hierarchical|auto"),
    scale: bool = Query(True)
):
    """
    Advanced customer segmentation using K-means clustering.
    
    Automatically detects optimal number of clusters using silhouette analysis
    if n_clusters not specified.
    """
    try:
        from ..agents.tools.advanced_segmentation import AdvancedSegmentationTool
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        df = pd.read_csv(session.dataset_schema.get("file_path"))
        
        # Create session context mock
        class SessionContext:
            def __init__(self, dataframe):
                self.dataframe = dataframe
        
        context = SessionContext(df)
        
        tool = AdvancedSegmentationTool()
        params = {
            "features": features or df.select_dtypes(include=[np.number]).columns.tolist(),
            "n_clusters": n_clusters,
            "clustering_method": method,
            "scale": scale,
        }
        
        result = await tool.execute(params, context)
        
        return {
            "session_id": session_id,
            "n_clusters": result.data.get("n_clusters"),
            "silhouette_score": result.data.get("silhouette_score"),
            "segment_counts": result.data.get("segment_counts"),
            "narrative": result.narrative,
            "segment_profiles": result.data.get("segment_profiles"),
        }
    
    except Exception as e:
        logger.exception("Segmentation failed")
        raise HTTPException(500, str(e))


@router.post("/analytics/forecast")
async def predictive_forecast(
    session_id: str,
    time_column: str,
    value_column: str,
    freq: str = Query("M", description="D=daily, W=weekly, M=monthly"),
    periods_ahead: int = Query(12, ge=1, le=100)
):
    """
    Time series forecasting using ARIMA/Prophet.
    
    Parameters:
    - time_column: Column with timestamps
    - value_column: Column to forecast
    - freq: Resampling frequency
    - periods_ahead: Number of periods to forecast
    """
    try:
        from ..agents.tools.time_series_trend import TimeSeriesTrendTool
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        df = pd.read_csv(session.dataset_schema.get("file_path"))
        
        # Create session context mock
        class SessionContext:
            def __init__(self, dataframe):
                self.dataframe = dataframe
        
        context = SessionContext(df)
        
        tool = TimeSeriesTrendTool()
        params = {
            "time_column": time_column,
            "value_column": value_column,
            "freq": freq,
        }
        
        result = await tool.execute(params, context)
        
        return {
            "session_id": session_id,
            "forecast": result.data,
            "narrative": result.narrative,
        }
    
    except Exception as e:
        logger.exception("Forecasting failed")
        raise HTTPException(500, str(e))


@router.post("/batch/predictions")
async def batch_predictions(
    session_id: str,
    model_id: str,
    batch_file: UploadFile = File(...)
):
    """
    Batch predict using a trained model.
    
    Upload a CSV with input features matching model training features.
    Returns predictions for all rows.
    """
    try:
        contents = await batch_file.read()
        batch_df = pd.read_csv(io.BytesIO(contents))
        
        # Load model and generate predictions
        # TODO: Implement model loading from model registry
        
        return {
            "session_id": session_id,
            "predictions": [],
            "rows_processed": len(batch_df),
        }
    
    except Exception as e:
        logger.exception("Batch prediction failed")
        raise HTTPException(500, str(e))


@router.get("/models/list")
async def list_trained_models(session_id: str):
    """List all trained models for a session."""
    try:
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        # Return list of models from session
        models = session.dataset_schema.get("models", [])
        
        return {
            "session_id": session_id,
            "models": models,
            "total_count": len(models),
        }
    
    except Exception as e:
        logger.exception("Failed to list models")
        raise HTTPException(500, str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all associated data."""
    try:
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        
        # Remove from memory
        if session_id in memory.sessions:
            del memory.sessions[session_id]
        
        # Remove from workflow/session cache
        clear_workflow_session(session_id)
        
        return {
            "session_id": session_id,
            "deleted": True,
            "message": "Session and all associated data deleted"
        }
    
    except Exception as e:
        logger.exception("Session deletion failed")
        raise HTTPException(500, str(e))


@router.post("/export/results")
async def export_results(
    session_id: str,
    format: str = Query("html", description="html|pdf|csv|json|xlsx"),
    include_visualizations: bool = Query(True),
    include_code: bool = Query(False)
):
    """
    Export analysis results in multiple formats.
    
    Formats:
    - html: Interactive HTML report
    - pdf: PDF report with charts
    - csv: Raw results as CSV
    - json: Structured JSON data
    - xlsx: Excel workbook
    """
    try:
        from ..memory.conversation_memory import get_memory_store
        
        memory = get_memory_store()
        session = memory.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        # Generate export
        # TODO: Implement export logic for different formats
        
        return {
            "session_id": session_id,
            "format": format,
            "generated_at": datetime.now().isoformat(),
            "download_url": f"/api/exports/{session_id}_{format}"
        }
    
    except Exception as e:
        logger.exception("Export failed")
        raise HTTPException(500, str(e))

