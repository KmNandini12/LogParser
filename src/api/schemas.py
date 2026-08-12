"""Pydantic v2 schemas for API requests and responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Payload for POST /api/v1/analyze."""

    raw_logs: Optional[str] = Field(
        default=None,
        description="Raw multiline application crash logs or stack traces.",
    )
    error_query: Optional[str] = Field(
        default=None,
        description="Explicit error message, exception, or error code.",
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of matching historical incidents to retrieve.",
    )


class IncidentMatch(BaseModel):
    """Retrieved post-mortem incident match."""

    id: int
    title: str
    service_name: str
    root_cause_summary: str
    remediation_steps: Optional[str] = None
    rrf_score: float


class LatencyBreakdown(BaseModel):
    """Execution latency profile across each pipeline stage."""

    log_parsing_ms: float
    anomaly_check_ms: float
    hybrid_retrieval_ms: float
    summarization_ms: float
    total_latency_ms: float


class AnalyzeResponse(BaseModel):
    """Structured response from POST /api/v1/analyze."""

    analysis_id: str
    report_markdown: str
    probable_root_cause: str
    affected_services: List[str]
    remediation_steps: List[str]
    anomalies_detected: List[Dict[str, Any]]
    retrieved_incidents: List[IncidentMatch]
    latency_breakdown_ms: LatencyBreakdown
    total_api_cost_usd: float = 0.0
    engine_source: str


class HealthResponse(BaseModel):
    """System health check response."""

    status: str
    postgres_connected: bool
    redis_connected: bool
    bm25_documents_indexed: int
    ollama_online: bool
