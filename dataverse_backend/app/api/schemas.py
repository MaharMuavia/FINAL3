"""Pydantic schemas for DataVerse AI API."""
from __future__ import annotations

from typing import Any
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
    service: str
    version: str
