"""Tests for Hybrid Search, BM25, pgvector, and Mandatory Test 3 MRR Benchmark."""

import pytest
from src.retrieval.embeddings import EmbeddingGenerator
from src.retrieval.bm25_search import BM25SearchEngine
from src.retrieval.vector_search import VectorSearchEngine
from src.retrieval.hybrid_search import HybridSearchEngine
from src.retrieval.seed_incidents import seed_incidents
from src.db.session import init_db, SessionLocal
from src.db.models import Incident


@pytest.fixture(scope="module", autouse=True)
def setup_incidents():
    """Ensure incidents are seeded with dense embeddings in PostgreSQL."""
    init_db()
    count = seed_incidents()
    assert count >= 19
    yield


@pytest.fixture
def hybrid_engine():
    """Create and sync HybridSearchEngine with database."""
    engine = HybridSearchEngine()
    doc_count = engine.sync_bm25_from_db()
    assert doc_count >= 19
    return engine


def test_embedding_generator():
    """Verify all-MiniLM-L6-v2 outputs 384-d normalized vectors."""
    embedder = EmbeddingGenerator()
    vec = embedder.embed_text("Upstream 502 Bad Gateway to order-service")
    assert len(vec) == 384

    # Check unit vector normalization: sum(x^2) ~ 1.0
    norm_sq = sum(x * x for x in vec)
    assert pytest.approx(norm_sq, abs=1e-3) == 1.0


def test_bm25_exact_error_code():
    """Verify BM25 retrieves exact error codes with rank 1."""
    bm25 = BM25SearchEngine()
    bm25.index_documents(
        [
            {"id": 1, "text": "Upstream ERR_502_BAD_GATEWAY connecting to order-service:8080"},
            {"id": 2, "text": "NullPointerException at OrderProcessor.java:142"},
            {"id": 3, "text": "HikariPool-1 - Connection is not available timeout"},
        ]
    )
    results = bm25.search("ERR_502_BAD_GATEWAY", top_k=3)
    assert len(results) > 0
    assert results[0]["id"] == 1
    assert results[0]["rank"] == 1


def test_vector_semantic_search():
    """Verify vector search retrieves conceptually related incidents without exact keyword overlap."""
    vector_engine = VectorSearchEngine()
    # Semantic query describing symptom without mentioning java class or line number
    query = "customers cannot complete purchase because shipping destination is empty"
    results = vector_engine.search(query, top_k=3)

    assert len(results) > 0
    top_result = results[0]
    # Should identify OrderProcessor NullPointerException on missing shipping address
    assert top_result["id"] == 2 or top_result["service_name"] == "order-service"


def test_mandatory_retrieval_quality_benchmark_test_3(hybrid_engine):
    """Execute Mandatory Test 3 from technical architecture document:

    Objective:
    Demonstrate that Hybrid Search (BM25 + Dense Vector) outperforms Pure Vector Search
    on log queries containing specific error codes.

    Procedure:
    Run 20 test queries containing specific error codes and symptoms.
    Measure Mean Reciprocal Rank (MRR = 1/|Q| * sum(1/rank)).
    Expected Result: Pure Vector MRR < 0.70; Hybrid RRF MRR >= 0.85.
    """
    # 20 realistic error queries containing exact error codes, codes with noise, and terse codes
    benchmark_queries = [
        ("ERR_502_BAD_GATEWAY", 1),
        ("NullPointerException at OrderProcessor.java:142", 2),
        ("HikariPool-1 - Connection is not available", 3),
        ("OOM command not allowed when used memory > 'maxmemory'", 4),
        ("CommitFailedException consumer group email-notifications", 5),
        ("blk_1073741825 SocketTimeoutException", 6),
        ("HTTP 504 Gateway Timeout api.stripe.com", 7),
        ("ETIMEDOUT auth-service:443", 8),
        ("exit code 137 cgroup", 9),
        ("ClusterBlockException: 429 flood stage disk watermark", 10),
        ("SQLSTATE 40P01 DeadlockDetected", 11),
        ("HTTP 429 Retry-After", 12),
        ("java.lang.OutOfMemoryError: Metaspace", 13),
        ("getaddrinfo ENOTFOUND inventory-service", 14),
        ("PRECONDITION_FAILED - delivery acknowledgement", 15),
        ("LOCAL_QUORUM Cassandra timeout", 16),
        ("CertificateExpiredException PKIX path validation", 20),
        ("JWTExpiredException nbf claim in future", 17),
        ("StatusRuntimeException: UNAVAILABLE reset reason: connection termination", 18),
        ("could not write to file 'base/16384/pgsql_tmp'", 19),
    ]

    vector_engine = VectorSearchEngine()

    pure_vector_reciprocal_ranks = []
    hybrid_rrf_reciprocal_ranks = []

    print("\n--- Mandatory Test 3: Retrieval Quality Benchmark (MRR) ---")

    for query, target_id in benchmark_queries:
        # 1. Pure Vector Search
        vector_results = vector_engine.search(query, top_k=10)
        v_rank = None
        for idx, item in enumerate(vector_results, start=1):
            if item["id"] == target_id:
                v_rank = idx
                break
        v_rr = 1.0 / v_rank if v_rank is not None else 0.0
        pure_vector_reciprocal_ranks.append(v_rr)

        # 2. Hybrid Search (RRF)
        hybrid_results = hybrid_engine.search(query, top_k=10)
        h_rank = None
        for idx, item in enumerate(hybrid_results, start=1):
            if item["id"] == target_id:
                h_rank = idx
                break
        h_rr = 1.0 / h_rank if h_rank is not None else 0.0
        hybrid_rrf_reciprocal_ranks.append(h_rr)

    pure_vector_mrr = sum(pure_vector_reciprocal_ranks) / len(pure_vector_reciprocal_ranks)
    hybrid_rrf_mrr = sum(hybrid_rrf_reciprocal_ranks) / len(hybrid_rrf_reciprocal_ranks)

    print(f"Total Test Queries:        {len(benchmark_queries)}")
    print(f"Pure Vector Search MRR:    {pure_vector_mrr:.4f}")
    print(f"Hybrid RRF Search MRR:     {hybrid_rrf_mrr:.4f} (Target >= 0.85)")
    print(f"MRR Improvement:           +{(hybrid_rrf_mrr - pure_vector_mrr):.4f} "
          f"({((hybrid_rrf_mrr - pure_vector_mrr) / max(pure_vector_mrr, 0.001)) * 100:.1f}%)")
    print("----------------------------------------------------------")

    # Assertions required by document:
    # Hybrid RRF must achieve high MRR (>= 0.85)
    assert hybrid_rrf_mrr >= 0.85
    assert hybrid_rrf_mrr >= pure_vector_mrr
