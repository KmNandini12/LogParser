"""API route definitions for LogParser service."""

import time
import uuid
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    IncidentMatch,
    LatencyBreakdown,
)
from src.parser import LogParser
from src.anomaly import AnomalyTracker
from src.retrieval.hybrid_search import HybridSearchEngine
from src.llm.client import OllamaClient
from src.llm.prompts import build_rca_prompt
from src.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Service singletons
_parser: LogParser = LogParser()
_tracker: AnomalyTracker = AnomalyTracker()
_hybrid_engine: HybridSearchEngine = HybridSearchEngine()
_llm_client: OllamaClient = OllamaClient()

# Ensure BM25 index is populated
try:
    _hybrid_engine.sync_bm25_from_db()
except Exception as e:
    logger.warning(f"Could not initialize BM25 during startup: {e}")


@router.get("/health", response_model=HealthResponse, tags=["Observability"])
async def health_check(db: Session = Depends(get_db)):
    """Check connectivity to PostgreSQL, Redis, and Ollama."""
    # 1. PostgreSQL check
    pg_ok = False
    try:
        db.execute(text("SELECT 1;"))
        pg_ok = True
    except Exception:
        pg_ok = False

    # 2. Redis check
    redis_ok = False
    try:
        redis_ok = bool(_tracker.redis.ping())
    except Exception:
        redis_ok = False

    # 3. BM25 count
    doc_count = len(_hybrid_engine.bm25.documents) if _hybrid_engine.bm25 else 0

    # 4. Ollama availability
    ollama_ok = await _llm_client.is_available()

    overall_status = "healthy" if (pg_ok and redis_ok) else "degraded"

    return HealthResponse(
        status=overall_status,
        postgres_connected=pg_ok,
        redis_connected=redis_ok,
        bm25_documents_indexed=doc_count,
        ollama_online=ollama_ok,
    )


@router.post(
    "/api/v1/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Analysis"],
)
async def analyze_incident(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
):
    """End-to-end incident analysis pipeline.

    1. Parses incoming logs into generalized templates (Drain3).
    2. Measures statistical arrival spikes (Redis Z-Score).
    3. Retrieves matching historical incidents via Hybrid Search (BM25 + pgvector RRF).
    4. Generates a deterministic 3-part RCA report using local Llama 3.2.
    """
    if not request.raw_logs and not request.error_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'raw_logs' or 'error_query' must be provided.",
        )

    analysis_id = str(uuid.uuid4())
    t_start = time.perf_counter()

    # --- STAGE 1: Log Parsing (Drain3) ---
    t0 = time.perf_counter()
    extracted_templates = []
    lines = (request.raw_logs or "").strip().split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    for line in cleaned_lines:
        res = _parser.parse_line(line)
        if res["template_id"] != -1:
            extracted_templates.append(res)
    t_parse = (time.perf_counter() - t0) * 1000.0

    # --- STAGE 2: Anomaly Detection (Redis Z-Score) ---
    t1 = time.perf_counter()
    anomalies_detected = []
    unique_template_ids = {t["template_id"] for t in extracted_templates}

    for tid in unique_template_ids:
        # Record occurrence and check Z-Score
        _tracker.record_occurrence(tid, count=1)
        anomaly_metric = _tracker.check_anomaly(tid)
        if anomaly_metric["is_anomaly"]:
            anomalies_detected.append(anomaly_metric)
    t_anomaly = (time.perf_counter() - t1) * 1000.0

    # --- STAGE 3: Hybrid Retrieval (BM25 + pgvector RRF) ---
    t2 = time.perf_counter()
    # Formulate retrieval query from error_query or extracted templates
    query_parts = []
    if request.error_query:
        query_parts.append(request.error_query)
    for t in extracted_templates[:3]:
        query_parts.append(t["template_str"])

    retrieval_query = " ".join(query_parts) if query_parts else "system crash error"

    # Ensure BM25 has documents if not synced yet
    if not _hybrid_engine.bm25 or not _hybrid_engine.bm25.documents:
        _hybrid_engine.sync_bm25_from_db(db=db)

    fused_incidents = _hybrid_engine.search(
        query=retrieval_query,
        top_k=request.top_k,
        db=db,
    )
    t_retrieval = (time.perf_counter() - t2) * 1000.0

    # --- STAGE 4: Local LLM Summarization ---
    t3 = time.perf_counter()
    rca_prompt = build_rca_prompt(
        log_query=retrieval_query,
        templates=extracted_templates,
        anomalies=anomalies_detected,
        matched_incidents=fused_incidents,
    )

    llm_output = await _llm_client.generate_rca(
        prompt=rca_prompt,
        matched_incidents=fused_incidents,
        anomalies=anomalies_detected,
    )
    t_summarize = (time.perf_counter() - t3) * 1000.0

    t_total = (time.perf_counter() - t_start) * 1000.0

    # Format incident matches for response
    matched_models = [
        IncidentMatch(
            id=inc["id"],
            title=inc["title"],
            service_name=inc["service_name"],
            root_cause_summary=inc["root_cause_summary"],
            remediation_steps=inc.get("remediation_steps"),
            rrf_score=inc["rrf_score"],
        )
        for inc in fused_incidents
    ]

    return AnalyzeResponse(
        analysis_id=analysis_id,
        report_markdown=llm_output["report_markdown"],
        probable_root_cause=llm_output["probable_root_cause"],
        affected_services=llm_output["affected_services"],
        remediation_steps=llm_output["remediation_steps"],
        anomalies_detected=anomalies_detected,
        retrieved_incidents=matched_models,
        latency_breakdown_ms=LatencyBreakdown(
            log_parsing_ms=round(t_parse, 2),
            anomaly_check_ms=round(t_anomaly, 2),
            hybrid_retrieval_ms=round(t_retrieval, 2),
            summarization_ms=round(t_summarize, 2),
            total_latency_ms=round(t_total, 2),
        ),
        total_api_cost_usd=0.00,  # Zero-cost local execution
        engine_source=llm_output.get("engine_source", "local"),
    )
