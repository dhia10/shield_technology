# Shield Technology — Security Telemetry Ingestion & Anomaly Detection

This repository contains the backend telemetry ingestion pipeline and anomaly detection worker developed during an engineering internship at Shield Technology (June – September 2026). The system collects high-frequency telemetry events from distributed network probes and endpoint agents, sanitizes sensitive data in real time, decouples persistence via an asynchronous queue, and scores anomalous behaviors using Machine Learning.

## Architecture & Components

The application source code is structured in the `app/` directory:

- `app/main.py` & `app/security.py`: FastAPI application exposing ingestion, query, analytical, and operational endpoints (`POST /api/v1/telemetry/ingest`, `GET /api/v1/telemetry/history`, `GET /api/v1/telemetry/stats`, `GET /api/v1/telemetry/dlq`, `POST /api/v1/telemetry/archive`, `GET /api/v1/health`, `GET /metrics`). Requests are authenticated via `X-API-Key` and verified for cryptographic payload integrity using `HMAC-SHA256` (`X-HMAC-Signature`).
- `app/schemas.py` & `app/parser.py`: Strict schema validation using Pydantic v2. The parser performs recursive redaction of sensitive credentials (`password`, `token`, `secret`, `api_key`, `access_token` replaced with `***REDACTED***`), enriches source IPs (network classification and geo-tagging), and computes a deterministic SHA-256 hash (`event_hash`) for deduplication.
- `app/broker.py` & `app/worker.py`: Asynchronous message queue abstraction with RabbitMQ integration and an in-memory queue fallback for local execution. The background worker drains queued events in configurable batches and routes corrupt or malformed payloads to a Dead Letter Queue (DLQ).
- `app/ml_scorer.py`: Machine Learning anomaly detection engine. Extracts a 7-dimensional feature vector from each event (including Shannon entropy of the payload string). Employs an `IsolationForest` model (`scikit-learn`) with multi-factor scoring fusion, automatically escalating event severity to `CRITICAL` whenever the anomaly score exceeds `0.80`.
- `app/repository.py`, `app/cache.py` & `app/archiver.py`: PostgreSQL persistence layer implemented with SQLAlchemy 2.0 Async (`asyncpg`), utilizing bulk upsert transactions (`ON CONFLICT DO UPDATE`) and composite indexing on `(timestamp, severity, event_type)`. Includes Base64 opaque cursor pagination, Redis caching for aggregated stats (TTL 300s) with automatic invalidation, and Gzip log archiving with SHA-256 checksum verification.

## Installation & Quickstart

### Running with Docker Compose

To build and run the complete stack (API, Worker, PostgreSQL, Redis, RabbitMQ, and Prometheus):

```bash
docker compose up --build -d
```

Services will be accessible at:
- API & Documentation: `http://localhost:8000/docs`
- Prometheus Metrics: `http://localhost:8000/metrics`
- Prometheus Server: `http://localhost:9090`
- RabbitMQ Management: `http://localhost:15672`

### Running Locally

1. Create and activate a virtual environment:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the API server:

```bash
uvicorn app.main:app --reload --port 8000
```

## Tests & Benchmarks

### Automated Test Suite

Run the test suite with coverage reporting:

```bash
pytest tests/test_pipeline.py -v --cov=app --cov-report=term-missing
```

The test suite validates schema parsing, credential masking, HMAC security, bulk upserts, cursor pagination, rate limiting, DLQ routing, Isolation Forest anomaly scoring, and autonomous severity escalation (19 passed, 90% code coverage).

### Stress Testing & Report Artifacts

Run the high-frequency synthetic attack load simulator (10,000 events):

```bash
python scripts/stress_test.py
```

Generate execution snapshots, benchmark metrics, and report artifacts into `rapport_snapshots/`:

```bash
python scripts/generate_report_artifacts.py
```

## Repository Structure

```text
├── app/
│   ├── archiver.py        # Log archiving and SHA-256 checksum sealing
│   ├── broker.py          # Message broker interface and DLQ handling
│   ├── cache.py           # Redis cache and in-memory fallback
│   ├── database.py        # SQLAlchemy async engine and session factory
│   ├── main.py            # FastAPI routes and middleware configuration
│   ├── metrics.py         # Prometheus metrics instrumentation
│   ├── ml_scorer.py       # Isolation Forest and Shannon entropy scoring
│   ├── models.py          # SQLAlchemy ORM models and composite indexes
│   ├── parser.py          # Pydantic parsing, redaction, and IP enrichment
│   ├── rate_limiter.py    # Sliding window rate limiter
│   ├── repository.py      # Bulk upsert and cursor-based history queries
│   ├── schemas.py         # Pydantic v2 event and response models
│   ├── security.py        # HMAC-SHA256 and API key authentication
│   └── worker.py          # Asynchronous batch processing worker
├── deploy/
│   └── prometheus.yml     # Prometheus scraping configuration
├── docs/
│   └── DAT_Architecture.md# Technical architecture document
├── rapport_snapshots/     # Verified benchmark traces and metrics snapshots
├── scripts/
│   ├── generate_report_artifacts.py # Report snapshots generator
│   └── stress_test.py               # High-frequency telemetry load simulator
├── tests/
│   └── test_pipeline.py   # Automated test suite (19 tests)
├── docker-compose.yml     # Multi-service container orchestration
├── Dockerfile             # Multi-stage container build
└── requirements.txt       # Project dependencies
```
