# Phase 2 Summary: Redis Anomaly Tracker & Database Schema

**Status:** Completed  
**Date:** 2026-07-05  
**Components Covered:** SQLAlchemy 2.0 Schema, pgvector Support, Redis Sliding Window, Statistical Z-Score Engine, End-to-End Ingestion Pipeline  

---

## 1. What We Built in Phase 2

### 1.1 SQLAlchemy 2.0 Database Layer (`src/db/`)
We established the dual relational and vector database schema inside PostgreSQL 16:
- **`src/db/session.py`**:
  - Configures SQLAlchemy engine with connection pooling (`pool_size=10, max_overflow=20, pool_pre_ping=True`).
  - `init_db()`: Automatically ensures PostgreSQL's `vector` extension is created before table generation.
  - Safe session generator `get_db()`.
- **`src/db/models.py`**:
  - **`LogTemplate` (`log_templates`)**:
    - `template_id` (PK, Integer): Aligns directly with Drain3 cluster IDs.
    - `pattern_str` (Text): Parameterized template string.
    - `occurrence_count` (Integer): Total instances observed.
    - `is_anomaly` (Boolean, indexed): Set to `True` when the statistical $Z$-score surpasses 3.0.
    - `first_seen`, `last_seen` (DateTime with timezone).
    - `embedding` (`Vector(384)`): Prepares the schema for Phase 3 dense vector retrieval.
  - **`Incident` (`incidents`)**:
    - `id` (PK, Integer, autoincrement).
    - `title` (String(255)): Incident title.
    - `service_name` (String(100), indexed): Affected service boundary.
    - `root_cause_summary` (Text): Post-mortem root cause description.
    - `remediation_steps` (Text): Troubleshooting checklist.
    - `content_embedding` (`Vector(384)`): Vector representation of post-mortem.

### 1.2 Redis Rolling Window Anomaly Engine (`src/anomaly.py`)
- **Time Bucket Partitioning**:
  - Ingestion counts are indexed into 10-second discrete buckets: `bucket_id = int(timestamp // 10)`.
  - Rolling window spans 5 minutes ($30 \times 10\text{s} = 300\text{s}$).
  - Uses Redis Hashes (`template:{id}:buckets`) with an automatic TTL of 10 minutes (`hash_ttl = 600s`) to prevent memory leaks.
- **Statistical $Z$-Score Calculation**:
  - Extracts baseline counts across historical window buckets: $[c_0, c_1, \dots, c_{28}]$.
  - Calculates window mean ($\mu$) and standard deviation ($\sigma$):
    $$\mu = \frac{1}{N}\sum_{i=0}^{N-1} c_i \quad\quad \sigma = \sqrt{\frac{1}{N}\sum_{i=0}^{N-1}(c_i - \mu)^2}$$
  - Computes active rate deviation:
    $$Z = \frac{c_{\text{current}} - \mu}{\max(\sigma, 1.0)}$$
  - If $Z \ge 3.0$, the event is flagged as an active anomaly.
  - Zero-division guard: protects against crashes when baseline rate variance is 0.

### 1.3 Integrated Pipeline (`src/pipeline.py`)
- Glues the three components together:
  1. `LogParser.parse_line(raw_log)` $\implies$ extracts template ID.
  2. `AnomalyTracker.record_occurrence(template_id)` $\implies$ updates 10-second bucket and calculates active $Z$-score.
  3. `SessionLocal` upserts `LogTemplate` into PostgreSQL, updating counts, timestamps, and setting `is_anomaly = True` when $Z \ge 3.0$.

---

## 2. Quantitative Verification Results

We added 7 new integration and benchmark tests (bringing total tests to 14):

```text
tests/test_anomaly.py::test_record_and_window_retrieval PASSED
tests/test_anomaly.py::test_zero_division_guard PASSED
tests/test_anomaly.py::test_steady_traffic_does_not_trigger_anomaly PASSED
tests/test_anomaly.py::test_mandatory_burst_anomaly_sensitivity_test_2 PASSED
tests/test_db.py::test_log_template_crud_and_vector PASSED
tests/test_db.py::test_incident_crud_and_similarity PASSED
tests/test_pipeline.py::test_pipeline_single_log PASSED
```

### Mandatory Test 2: Anomaly Detection Sensitivity Results
| Metric | Specification Target | Measured Test Value | Status |
| :--- | :--- | :--- | :--- |
| **Normal Traffic Baseline** | Steady ~10 logs/sec for 3 mins | $\mu = 61.21$ logs/bucket, $\sigma = 47.92$ | Verified |
| **Burst Injection** | 500 error logs in 5s | $x = 500$ logs | Injected |
| **Peak $Z$-Score** | $Z \ge 3.0$ | **$Z = 9.16$** | **PASSED** |
| **Anomaly Trigger** | `is_anomaly = True` | **`True`** (within 5 seconds) | **PASSED** |

---

## 3. How to Run & Verify Phase 2

1. **Run Full Test Suite:**
   ```bash
   .\.venv\Scripts\pytest -v -s tests/
   ```
2. **Inspect Database Schema:**
   ```bash
   .\.venv\Scripts\python -c "from src.db.session import init_db; init_db()"
   ```
3. **Execute Anomaly Sensitivity Test Individually:**
   ```bash
   .\.venv\Scripts\pytest -v -s tests/test_anomaly.py -k "test_mandatory_burst_anomaly_sensitivity_test_2"
   ```
