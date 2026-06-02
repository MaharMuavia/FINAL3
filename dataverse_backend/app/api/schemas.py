"""Pydantic schemas for request and response payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str
    expires_in: int  # seconds


class TokenData(BaseModel):
    """JWT token payload."""
    username: Optional[str] = None


class User(BaseModel):
    """User schema (public response)."""
    id: Optional[str] = None
    username: str
    email: str
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    """User registration schema."""
    username: str
    email: EmailStr
    full_name: str
    password: str


class UserLogin(BaseModel):
    """User login schema."""
    username: str
    password: str


class UserInDB(User):
    """User with hashed password (internal use)."""
    hashed_password: str


# Dataset & Analysis schemas
class UploadResponse(BaseModel):
    session_id: str
    success: bool
    message: str
    is_retail: bool
    matched_keywords: Optional[List[str]] = None
    dataset_filename: Optional[str] = None
    dataset_rows: Optional[int] = None
    dataset_cols: Optional[int] = None
    dataset_id: Optional[str] = None
    column_names: Optional[List[str]] = None
    column_dtypes: Optional[List[str]] = None
    dataset_preview: Optional[List[Dict[str, Any]]] = None
    dataset_profile: Optional[Dict[str, Any]] = None
    dataset_type: Optional[str] = None
    column_roles: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None


# Chat/Conversation schemas
class MessageCreate(BaseModel):
    """Create a new message in conversation."""
    content: str
    message_type: str = "text"
    
class MessageResponse(BaseModel):
    """Message response."""
    id: str
    role: str
    content: str
    message_type: str
    created_at: str
    payload_json: Optional[Dict] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    """Create a conversation."""
    dataset_id: Optional[str] = None
    title: Optional[str] = None


class ConversationResponse(BaseModel):
    """Conversation response."""
    id: str
    title: Optional[str]
    dataset_id: Optional[str]
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class QueryRequest(BaseModel):
    session_id: str
    query: str


class QueryResponse(BaseModel):
    session_id: str
    intent: Dict[str, Any]
    computed_facts: Dict[str, Any]
    report: str
    action_required: Optional[str] = None
    candidates: Optional[List[str]] = None
    is_retail: Optional[bool] = None


class SessionStatusResponse(BaseModel):
    session_id: str
    dataset: Optional[Dict[str, Any]] = None
    dataset_is_retail: Optional[bool] = None
    retail_validation: Optional[Dict[str, Any]] = None
    execution_trace: Optional[List[str]] = None
    eda_completed: Optional[bool] = None
    preprocessing_completed: Optional[bool] = None


class ConfirmColumnRequest(BaseModel):
    session_id: str
    column_name: str


class ConfirmColumnResponse(BaseModel):
    session_id: str
    column_name: str
    message: str


class HealthResponse(BaseModel):
    status: str
    details: Optional[Dict[str, Any]] = None


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
