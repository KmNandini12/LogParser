# Phase 1 Summary: Environment Setup & Log Parsing Pipeline

**Status:** Completed  
**Date:** 2026-06-15  
**Components Covered:** Infrastructure, Log Parsing Engine, Benchmark Datasets, Test Suite  

---

## 1. What We Built in Phase 1

### 1.1 Multi-Container Infrastructure (`docker-compose.yml`)
We provisioned isolated, reproducible Docker services:
- **PostgreSQL 16 with pgvector (`pgvector/pgvector:pg16`):**
  - Host Port: `5433` $\rightarrow$ Container Port `5432`
  - Health check: `pg_isready`
  - Extension verified: `vector` v0.8.7 active and ready for 384-dimensional embeddings.
- **Redis 7 (`redis:7-alpine`):**
  - Host Port: `6380` $\rightarrow$ Container Port `6379`
  - Health check: `redis-cli ping`
  - Verified response: `PONG` (True)
  - Dedicated to the rolling 5-minute template frequency buckets for anomaly detection.

### 1.2 Configuration & Environment
- [`.env`](file:///d:/Projects/LogParser/.env) & [`.env.example`](file:///d:/Projects/LogParser/.env.example): Contains all environment configurations (database URLs, Redis host/ports, Ollama host/model, Drain3 config path).
- [`src/config.py`](file:///d:/Projects/LogParser/src/config.py): Centralized Python settings module loading `.env` with type casting and safe fallback defaults.

### 1.3 Online Log Template Mining Engine (`drain3`)
- [`config/drain3.ini`](file:///d:/Projects/LogParser/config/drain3.ini): Configures IBM's Drain algorithm:
  - **Tree Depth (`depth = 4`):** Determines the maximum parse tree depth for token clustering.
  - **Similarity Threshold (`sim_th = 0.5`):** Tokens must share at least 50% non-masked structure to cluster together.
  - **Dynamic Entity Masking Rules:** Pre-filters raw logs using regular expressions before tree traversal:
    - IPv4/IPv6 Addresses: replaced with `<IP>`
    - UUIDs/GUIDs: replaced with `<UUID>`
    - Hexadecimal pointers (`0x[a-f0-9]+`): replaced with `<HEX>`
    - Numbers and Ports: replaced with `<NUM>`
    - ISO/Standard Timestamps: replaced with `<TIME>`
- [`src/parser.py`](file:///d:/Projects/LogParser/src/parser.py):
  - `LogParser.parse_line(raw_log)`: Streams a single line, matches or creates a cluster, extracts dynamic parameters, and returns structured data:
    ```python
    {
        "template_id": 1,
        "template_str": "Receiving block blk_<NUM> src: /<IP>:<NUM> dest: /<IP>:<NUM>",
        "change_type": "cluster_created",
        "cluster_size": 1,
        "parameters": ["1024", "10.0.0.1", "50010", "10.0.0.2", "50010"],
        "raw_log": "..."
    }
    ```
  - `LogParser.parse_file(file_path)`: Generator yielding structured results line-by-line with $O(1)$ memory overhead.
  - `LogParser.calculate_compression_ratio()`: Computes $1 - (\text{clusters} / \text{total\_lines})$.

### 1.4 Benchmark Testing Datasets
- [`data/sample_logs/sample_hdfs.log`](file:///d:/Projects/LogParser/data/sample_logs/sample_hdfs.log): 5,000 lines of simulated Hadoop Distributed File System operations.
- [`data/sample_logs/sample_microservice.log`](file:///d:/Projects/LogParser/data/sample_logs/sample_microservice.log): 5,000 lines of modern microservice logs (authentication, orders, payment timeouts, unhandled `NullPointerException` stack traces, and 502 bad gateways).
- [`data/sample_logs/HDFS_2k.log`](file:///d:/Projects/LogParser/data/sample_logs/HDFS_2k.log): The official Loghub 2,000-line production benchmark dataset.

---

## 2. Quantitative Verification Results

We implemented automated tests in [`tests/test_parser.py`](file:///d:/Projects/LogParser/tests/test_parser.py). All 7 tests passed:

```text
tests/test_parser.py::test_parser_initialization PASSED
tests/test_parser.py::test_parse_single_line_masking PASSED
tests/test_parser.py::test_identical_log_clustering PASSED
tests/test_parser.py::test_different_log_creates_new_cluster PASSED
tests/test_parser.py::test_empty_line_handling PASSED
tests/test_parser.py::test_compression_ratio_on_hdfs_benchmark PASSED
tests/test_parser.py::test_compression_ratio_on_official_loghub_2k PASSED
```

### Compression Metric Results (Fulfills Technical Doc Test 1):
| Dataset | Raw Log Lines | Extracted Unique Templates | Compression Ratio | Target |
| :--- | :--- | :--- | :--- | :--- |
| **Synthetic HDFS Stream** | 5,000 lines | 8 templates | **99.84%** | $\ge 90\%$ |
| **Loghub Official `HDFS_2k.log`** | 2,000 lines | 17 templates | **99.15%** | $\ge 90\%$ |

---

## 3. How to Run & Verify Phase 1

1. **Verify Docker Containers:**
   ```bash
   docker ps --filter "name=logparser"
   ```
2. **Run Pytest Suite:**
   ```bash
   .\.venv\Scripts\pytest -v -s tests/test_parser.py
   ```
3. **Verify Database & Redis Connections:**
   ```bash
   .\.venv\Scripts\python -c "import psycopg2, redis; print('Redis:', redis.Redis(port=6380).ping()); conn = psycopg2.connect('postgresql://postgres:postgrespassword@localhost:5433/logparser_db'); print('Postgres Connected!')"
   ```
