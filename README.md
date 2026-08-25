# Automated Cloud Incident & Log Root-Cause Analyzer (RCA)

An enterprise-grade, zero-cost, local-first log observability and automated incident root-cause analysis pipeline.

Built to solve the critical challenges of distributed systems post-mortems: high log volume, dynamic noise, un-indexed error spikes, and cloud LLM privacy/cost constraints.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Raw Streaming Log Files   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |    Drain3 Template Miner    |
                      |   (Masking: IP, UUID, Num)  |  --> 99%+ Log Compression
                      +--------------+--------------+
                                     |
                      +--------------+--------------+
                      |                             |
                      v                             v
       +----------------------------+  +----------------------------+
       |   Redis Anomaly Tracker    |  |     PostgreSQL + pgvector  |
       |  (Rolling Z-Score > 3.0)   |  |   (Templates & Post-Mortems|
       +--------------+-------------+  +--------------+-------------+
                      |                               |
                      +--------------+----------------+
                                     |
                                     v
                      +-----------------------------+
                      |     Hybrid Search Engine    |
                      |   BM25 Lexical + Cosine 384d|  --> Reciprocal Rank Fusion
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |     FastAPI / LLM Engine    |
                      | Ollama Llama-3.2-3B / Fallbk|  --> Zero API Cost
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  3-Part Actionable RCA:     |
                      |  1. Root Cause              |
                      |  2. Affected Services       |
                      |  3. Remediation Steps       |
                      +-----------------------------+
```

---

## Key Features & Benchmark Results

- **Drain3 Online Log Template Mining:** Extracts dynamic parameters (`<IP>`, `<UUID>`, `<HEX>`, `<NUM>`) into generalized log templates in $O(1)$ time. Achieved **99.84% compression ratio** on synthetic microservices logs and **99.15%** on official Loghub `HDFS_2k.log`.
- **Sliding-Window Z-Score Anomaly Detection:** 10-second Redis hash buckets across a 30-bucket (5-minute) rolling window. Sensitivity benchmark detected traffic bursts in **< 5 seconds** with **$Z = 9.16$** ($Z \ge 3.0$ threshold).
- **Hybrid Search (BM25 + pgvector) with RRF:** Fuses lexical token matching (exact error codes like `ERR_502_BAD_GATEWAY`) with dense vector semantics (`all-MiniLM-L6-v2`, 384d). Achieved **1.0000 MRR (Mean Reciprocal Rank)** across 20 validation queries (vs. 0.9750 pure vector baseline).
- **Zero-Cloud-Cost Local LLM RCA:** Async integration with Ollama (`llama3.2:3b`) with deterministic fallback synthesis. Generates structured SRE post-mortem reports with **\$0.00 API cost**.
- **End-to-End Latency:** Full 1,000-log parsing, anomaly tracking, hybrid retrieval, and RCA generation executes in **~1.84 seconds**.

---

## Tech Stack

- **Backend & API:** Python 3.11, FastAPI, Uvicorn, Pydantic v2
- **Log Parsing:** Drain3 (IBM)
- **Databases:** PostgreSQL 16 + pgvector, Redis 7 (Alpine)
- **Information Retrieval:** BM25 (`rank-bm25`), Sentence-Transformers (`all-MiniLM-L6-v2`), Reciprocal Rank Fusion ($k=60$)
- **LLM / Inference:** Ollama (`llama3.2:3b`), Async HTTPX
- **Orchestration & Testing:** Docker Compose, Pytest (21/21 passing tests)

---

## Repository Structure

```text
LogParser/
├── config/
│   └── drain3.ini             # Drain3 tree depth, sim threshold & regex masking rules
├── data/
│   ├── generate_samples.py    # Log dataset generators (HDFS & microservices)
│   ├── incidents_seed.json    # 20 historical post-mortem incident knowledge base
│   └── sample_logs/           # Benchmark datasets (HDFS_2k.log, synthetic logs)
├── docs/
│   ├── PHASE_1_SUMMARY.md     # Infrastructure & Drain3 pipeline details
│   ├── PHASE_2_SUMMARY.md     # Redis anomaly tracker & PostgreSQL schema
│   ├── PHASE_3_SUMMARY.md     # Hybrid search, embeddings & RRF retrieval
│   ├── PHASE_4_SUMMARY.md     # FastAPI gateway, Ollama integration & latency profile
│   └── ERRORS_AND_TRADEOFFS.md# All 14 engineering trade-offs & resolved bugs
├── src/
│   ├── api/                   # FastAPI routes & Pydantic request/response schemas
│   ├── db/                    # SQLAlchemy 2.0 ORM models & session management
│   ├── llm/                   # Ollama client, RCA prompts & fallback synthesizer
│   ├── retrieval/             # BM25, pgvector search, and RRF fusion engine
│   ├── anomaly.py             # Redis rolling-window Z-score detector
│   ├── config.py              # Environment settings & URL normalization
│   ├── parser.py              # Streaming Drain3 log template miner
│   ├── pipeline.py            # End-to-end ingestion orchestrator
│   └── main.py                # FastAPI application entrypoint with lifespan events
├── tests/                     # 21 automated pytest integration & benchmark tests
├── docker-compose.yml         # Container definitions (Postgres pgvector, Redis, API)
├── Dockerfile                 # Container image for API gateway
├── pytest.ini                 # Pytest configuration
└── requirements.txt           # Project dependencies
```

---

## Quickstart Guide

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+
- (Optional) [Ollama](https://ollama.com) with `llama3.2:3b`

### 2. Environment Setup
```bash
# Clone the repository
git clone <your-repo-url>
cd LogParser

# Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Start Database & Cache Containers
```bash
docker compose up -d postgres redis
```

### 4. Run Automated Test Suite (21 Tests)
```bash
pytest -v
```

### 5. Run the API Gateway
```bash
python -m uvicorn src.main:app --reload --port 8000
```
- Interactive API Docs (Swagger): `http://localhost:8000/docs`
- Health check: `GET http://localhost:8000/health`
- Incident Analysis: `POST http://localhost:8000/api/v1/analyze`

---

## License
MIT License.
