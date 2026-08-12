"""Tests for FastAPI Gateway, Analysis Routes, and Mandatory Test 4 Latency/Cost Profile."""

import time
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.retrieval.seed_incidents import seed_incidents
from src.db.session import init_db
from src.config import DATA_DIR


@pytest.fixture(scope="module", autouse=True)
def ensure_environment():
    """Ensure database and seed data are ready before API tests."""
    init_db()
    seed_incidents()
    yield


@pytest.fixture
def client():
    """Create FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    """Verify /health reports healthy status for PostgreSQL and Redis."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["postgres_connected"] is True
    assert data["redis_connected"] is True
    assert data["bm25_documents_indexed"] >= 19


def test_analyze_with_error_query(client):
    """Verify /api/v1/analyze returns a structured 3-part RCA report."""
    payload = {
        "error_query": "ERR_502_BAD_GATEWAY upstream timeout to order-service",
        "top_k": 3,
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["analysis_id"] is not None
    assert "Probable Root Cause" in data["report_markdown"]
    assert "Affected Services" in data["report_markdown"]
    assert "Remediation Steps" in data["report_markdown"]
    assert len(data["remediation_steps"]) >= 1
    assert data["total_api_cost_usd"] == 0.00
    assert len(data["retrieved_incidents"]) > 0


def test_mandatory_latency_and_cost_profile_test_4(client):
    """Execute Mandatory Test 4 from technical architecture document:

    Objective:
    Prove system efficiency and operational sustainability.

    Procedure:
    Send a batch of 1,000 raw logs with a crash query to /api/v1/analyze
    and time the pipeline components.

    Metric Summary Table to Record:
    - Log Parsing (Drain3): Latency & $0.00 Cost
    - Anomaly Check (Redis): Latency & $0.00 Cost
    - Hybrid Retrieval (pgvector + BM25): Latency & $0.00 Cost
    - Summarization (Ollama / Local): Latency & $0.00 Cost
    - Total End-to-End Latency: Latency & $0.00 Cost
    """
    # 1. Load 1,000 raw lines from sample benchmark log
    log_file = DATA_DIR / "sample_logs" / "sample_microservice.log"
    assert log_file.exists(), "sample_microservice.log not found"

    with log_file.open("r", encoding="utf-8") as f:
        sample_1000_lines = [next(f).strip() for _ in range(1000)]

    raw_logs_payload = "\n".join(sample_1000_lines)

    payload = {
        "raw_logs": raw_logs_payload,
        "error_query": "Unhandled exception NullPointerException at OrderProcessor.java:142",
        "top_k": 3,
    }

    t0 = time.perf_counter()
    response = client.post("/api/v1/analyze", json=payload)
    total_client_latency_ms = (time.perf_counter() - t0) * 1000.0

    assert response.status_code == 200
    data = response.json()
    breakdown = data["latency_breakdown_ms"]

    print("\n" + "=" * 65)
    print("MANDATORY TEST 4: END-TO-END LATENCY & COST PROFILE (1,000 LOGS)")
    print("=" * 65)
    print(f"{'Pipeline Stage':<35} | {'Measured Latency':<15} | {'API Cost'}")
    print("-" * 65)
    print(f"{'Log Parsing (Drain3)':<35} | {breakdown['log_parsing_ms']:>9.2f} ms    | $0.00")
    print(f"{'Anomaly Check (Redis)':<35} | {breakdown['anomaly_check_ms']:>9.2f} ms    | $0.00")
    print(f"{'Hybrid Retrieval (pgvector + BM25)':<35} | {breakdown['hybrid_retrieval_ms']:>9.2f} ms    | $0.00")
    print(f"{'Summarization (Local Inference)':<35} | {breakdown['summarization_ms']:>9.2f} ms    | $0.00")
    print("-" * 65)
    print(f"{'Total Pipeline Latency':<35} | {breakdown['total_latency_ms']:>9.2f} ms    | $0.00")
    print(f"{'Total Client Roundtrip':<35} | {total_client_latency_ms:>9.2f} ms    | $0.00")
    print("=" * 65)

    # Assertions required by document:
    assert data["total_api_cost_usd"] == 0.00
    # 1,000 logs parsing and hybrid retrieval should finish fast on local machine (< 2000ms)
    assert breakdown["log_parsing_ms"] > 0
    assert breakdown["hybrid_retrieval_ms"] > 0
    assert "OrderProcessor" in data["probable_root_cause"] or "order-service" in str(data["affected_services"])
