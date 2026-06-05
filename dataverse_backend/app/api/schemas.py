"""Pydantic schemas for DataVerse AI API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[str]
    profile: dict[str, Any]
    message: str = "Dataset uploaded and profiled successfully"


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str
    summary: str = ""
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    dataset_id: str
    row_count: int
    column_count: int
    columns: list[str]
    profile: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    service: str | None = None
    version: str | None = None
    details: dict[str, Any] | None = None


class AnalyzeUploadResponse(BaseModel):
    session_id: str
    filename: Optional[str] = None
    dataset_profile: Dict[str, Any]
    semantic_map: Optional[Dict[str, Any]] = None
    business_summary: Optional[Dict[str, Any]] = None
    business_metrics: Optional[Dict[str, Any]] = None
    query_plan: Optional[Dict[str, Any]] = None
    query_answer: Optional[Dict[str, Any]] = None
    data_quality: Dict[str, Any]
    eda: Dict[str, Any]
    trends: Dict[str, Any]
    correlations: Dict[str, Any]
    outliers: Dict[str, Any]
    target_suggestions: List[Dict[str, Any]]
    prediction: Dict[str, Any]
    xai: Dict[str, Any]
    charts: List[Dict[str, Any]]
    executive_summary: str
    key_insights: List[str]
    recommendations: List[str]
    warnings: List[str]
    next_questions: List[str]


class AnalyzeQueryRequest(BaseModel):
    session_id: str
    query: str
    target_column: Optional[str] = None
    task_type: Optional[str] = None
    run_predictions: Optional[bool] = None
    run_xai: Optional[bool] = None
    use_llm: bool = False
    provider: Optional[str] = None


class AnalyzeQueryResponse(AnalyzeUploadResponse):
    pass


class UploadProfileResponse(BaseModel):
    session_id: str
    filename: Optional[str] = None
    dataset_profile: Dict[str, Any]
    data_quality: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    detail: str


class ChatSessionCreate(BaseModel):
    title: str = "New Chat"


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatMessageCreate(BaseModel):
    content: str
    dataset_id: Optional[str] = None


class SessionAnalyzeRequest(BaseModel):
    dataset_id: Optional[str] = None
    user_prompt: str = "Analyze this dataset"
    run_xai: bool = True
    generate_report: bool = True


class DatasetProfileResponse(BaseModel):
    session_id: str
    profile: Dict[str, Any]


class CorrelationResponse(BaseModel):
    session_id: str
    correlations: Dict[str, Any]


class RecommendationResponse(BaseModel):
    session_id: str
    recommendations: List[str]
    key_findings: Dict[str, Any]


class TrainModelRequest(BaseModel):
    session_id: str
    target_column: str
    task_type: str = Field(default="classification", description="classification or regression")
    test_size: Optional[float] = Field(default=0.2, ge=0.1, le=0.5)


class TrainModelResponse(BaseModel):
    session_id: str
    task_type: str
    target_column: str
    status: str
    job_id: Optional[str] = None
    best_model: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    predictions_sample: Optional[List[Dict[str, Any]]] = None
    feature_importance: Optional[Dict[str, float]] = None
    error: Optional[str] = None


class MLJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class GraphExecuteRequest(BaseModel):
    session_id: str
    query: str
    thread_id: Optional[str] = None
    dataset_path_override: Optional[str] = None


class GraphExecuteResponse(BaseModel):
    session_id: str
    thread_id: str
    final_response: Optional[str] = None
    insights: List[str] = Field(default_factory=list)
    visualizations: List[Dict[str, Any]] = Field(default_factory=list)
    ml_results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    iteration_count: int = 0
