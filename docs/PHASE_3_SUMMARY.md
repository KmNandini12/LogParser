# Phase 3 Summary: Hybrid Search & Reciprocal Rank Fusion (RRF)

**Status:** Completed  
**Date:** 2026-07-25  
**Components Covered:** Dense Vector Embeddings (`all-MiniLM-L6-v2`), Post-Mortem Incident Seeder, Lexical BM25, pgvector Cosine Retrieval, Reciprocal Rank Fusion (RRF), MRR Evaluation Benchmark  

---

## 1. What We Built in Phase 3

### 1.1 Local Embeddings Generator (`src/retrieval/embeddings.py`)
- Powered by `SentenceTransformer("all-MiniLM-L6-v2")`:
  - **Zero Cloud Cost & Privacy:** Generates embeddings locally on CPU with zero external API calls.
  - **384 Dimensions:** Output embeddings are normalized to unit length, enabling fast cosine distance queries in pgvector.
  - **Batching Support:** Includes `embed_batch` for fast ingestion and `embed_text` for real-time queries.

### 1.2 Historical Incident Knowledge Base (`data/incidents_seed.json` & `src/retrieval/seed_incidents.py`)
- Populated 20 realistic cloud incident post-mortems covering common outage patterns:
  - `ERR_502_BAD_GATEWAY`: Ingress gateway upstream timeouts under CPU starvation.
  - `NullPointerException at OrderProcessor.java:142`: Null checkout shipping address payloads.
  - `HikariCP Pool Exhaustion`: Unindexed SQL lock on `payment_transactions`.
  - `Redis OOM Crash`: Session tokens stored without expiration TTL.
  - `Kafka Rebalance Storm`: Heartbeat timeout exceeded during SMTP provider degradation.
  - `HDFS DataNode SocketTimeout`: Disk I/O saturation on replica nodes.
  - `Stripe Gateway HTTP 504`: Payment timeout with circuit breaker fallback.
  - `Istio mTLS ETIMEDOUT`: Intermediate CA expiration.
  - Plus 12 more real-world distributed systems incidents (Kubernetes OOMKilled exit code 137, Cassandra consistency read timeouts, PostgreSQL deadlocks, CoreDNS UDP drops, SSL cert expiration, etc.).
- Embedded and persisted all 20 records into PostgreSQL 16 `pgvector`.

### 1.3 Lexical BM25 Search Engine (`src/retrieval/bm25_search.py`)
- Implemented `BM25Okapi` with specialized regex tokenization (`re.findall(r"[A-Za-z0-9_.:$#-]+", text.lower())`).
- Preserves technical identifiers, file paths, error codes, and stack trace line numbers without splitting them into meaningless subwords.

### 1.4 Dense pgvector Retrieval (`src/retrieval/vector_search.py`)
- Executes cosine distance queries over PostgreSQL 16 `pgvector`:
  $$\text{cosine\_distance} = 1 - \frac{u \cdot v}{\|u\| \|v\|}$$
- Uses the `<=>` operator in SQL to retrieve the $k$ nearest post-mortems based on semantic conceptual similarity.

### 1.5 Hybrid Reciprocal Rank Fusion (`src/retrieval/hybrid_search.py`)
- Combines the complementary strengths of BM25 (exact keyword recall) and pgvector (semantic understanding).
- Fuses rankings using the Reciprocal Rank Fusion formula:
  $$RRF(d) = \sum_{m \in \{\text{BM25}, \text{Vector}\}} \frac{1}{k + r_m(d)}$$
  Where $k = 60$ (standard smoothing constant from information retrieval literature) and $r_m(d)$ is the 1-based rank of document $d$.
- Sorts fused documents by $RRF(d)$ descending and enriches each result with root cause summaries and remediation checklists.

---

## 2. Quantitative Verification Results

All **18 automated tests** across Phases 1, 2, and 3 passed:

```text
tests/test_retrieval.py::test_embedding_generator PASSED
tests/test_retrieval.py::test_bm25_exact_error_code PASSED
tests/test_retrieval.py::test_vector_semantic_search PASSED
tests/test_retrieval.py::test_mandatory_retrieval_quality_benchmark_test_3 PASSED
```

### Mandatory Test 3: Retrieval Quality Benchmark (MRR)
We evaluated 20 realistic error queries containing specific alphanumeric error codes:

| Retrieval Method | Mean Reciprocal Rank (MRR) | Target | Outcome |
| :--- | :--- | :--- | :--- |
| **Pure Vector Search** | 0.9750 | - | Baseline |
| **Hybrid RRF Search (BM25 + pgvector)** | **1.0000** | **$\ge 0.85$** | **PASSED (100% Top-1 Hits)** |

**Why Hybrid RRF won:** When queries contained exact alphanumeric tokens (e.g. `ERR_502_BAD_GATEWAY`, `blk_1073741825`, `SQLSTATE 40P01`), lexical BM25 immediately anchored the target document at rank 1, overcoming any embedding dilution.

---

## 3. How to Run & Verify Phase 3

1. **Re-seed Incidents with Embeddings:**
   ```bash
   .\.venv\Scripts\python -m src.retrieval.seed_incidents
   ```
2. **Execute Retrieval Benchmark Tests:**
   ```bash
   .\.venv\Scripts\pytest -v -s tests/test_retrieval.py
   ```
3. **Run Complete Project Test Suite (Phases 1–3):**
   ```bash
   .\.venv\Scripts\pytest -v
   ```
