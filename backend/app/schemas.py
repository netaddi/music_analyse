from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TechnicalInfo(BaseModel):
    original_filename: str
    stored_filename: str
    extension: str
    format_name: str
    codec_name: str
    codec_long_name: str | None = None
    sample_rate: int
    channels: int
    duration_seconds: float
    bit_rate_kbps: float | None = None
    bits_per_sample: int | None = None
    channel_layout: str | None = None
    file_size_bytes: int


class AnalysisSummary(BaseModel):
    overall_score: float
    risk_level: str
    headline: str
    confidence: float
    estimated_platform_attenuation_db: float
    top_issue: str


class CategoryReport(BaseModel):
    slug: str
    name: str
    score: float
    severity: Literal["info", "minor", "moderate", "major"]
    summary: str
    details: str
    evidence: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence: float


class Recommendation(BaseModel):
    id: str
    category_slug: str
    title: str
    severity: Literal["info", "minor", "moderate", "major"]
    summary: str
    evidence: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    confidence: float


class ChartSeries(BaseModel):
    name: str
    values: list[float] = Field(default_factory=list)


class ChartData(BaseModel):
    kind: Literal["line", "bar"]
    title: str
    x_label: str
    y_label: str
    x: list[float] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    report_id: str
    created_at: datetime
    technical_info: TechnicalInfo
    summary: AnalysisSummary
    categories: list[CategoryReport]
    recommendations: list[Recommendation]
    charts: dict[str, ChartData]
    metrics: dict[str, Any]


class JobState(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str
    original_filename: str
    created_at: datetime
    updated_at: datetime
    report_id: str | None = None
    report_url: str | None = None
    error: str | None = None


class AnalyzeAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str
