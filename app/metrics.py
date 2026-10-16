"""
Shield Technology - Prometheus Metrics & Observability
Weeks 9-11: Prometheus metrics instrumentation (counters, histograms, gauges) for telemetry pipeline.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

# Prometheus Counters & Histograms
EVENTS_INGESTED_TOTAL = Counter(
    "telemetry_events_ingested_total",
    "Total security telemetry events ingested by the platform",
    ["severity", "event_type"],
)

INGEST_LATENCY_SECONDS = Histogram(
    "telemetry_ingest_latency_seconds",
    "Latency of the HTTP ingestion endpoint",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

DB_BULK_INSERT_DURATION_SECONDS = Histogram(
    "telemetry_db_bulk_insert_duration_seconds",
    "Time taken to execute database bulk upsert transactions",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

QUEUE_DEPTH_GAUGE = Gauge(
    "telemetry_queue_depth",
    "Current number of pending events waiting in the broker queue",
    ["queue_name"],
)

DLQ_EVENTS_TOTAL = Counter(
    "telemetry_dlq_events_total",
    "Count of malformed or poison events routed to the Dead Letter Queue",
    ["reason"],
)

RATE_LIMIT_EXCEEDED_TOTAL = Counter(
    "telemetry_rate_limit_exceeded_total",
    "Count of 429 Too Many Requests rejections due to rate limiting",
)


def get_prometheus_metrics() -> bytes:
    """Generates standard Prometheus metric output for scraping."""
    return generate_latest(REGISTRY)
