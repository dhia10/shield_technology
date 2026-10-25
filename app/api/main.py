"""
Shield Technology Master FastAPI Application.
Coordinates high-throughput telemetry ingestion, Isolation Forest ML threat scoring,
NumPy vectorized cosine similarity retrieval, Prometheus metrics, and live demo console.
"""

import asyncio
from contextlib import asynccontextmanager
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routers.demo import router as demo_router
from app.api.routers.health import router as health_router
from app.api.routers.search import router as search_router
from app.api.routers.telemetry import router as telemetry_router
from app.core.config import settings
from app.storage.cache import cache_service
from app.storage.database import init_db
from app.workers.broker import message_broker
from app.workers.worker import telemetry_worker


# Webhook Alert Callback when queue reaches critical capacity
async def trigger_queue_alert_webhook(alert_message: str):
    print(f"[SECURITY ALERT WEBHOOK DISPATCHED] -> {alert_message}")


message_broker.webhook_alert_callback = trigger_queue_alert_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & background worker lifecycle hooks."""
    # 1. Initialize DB Schema
    await init_db()
    # 2. Connect Cache
    await cache_service.connect()
    # 3. Start Background Worker Loop
    worker_task = asyncio.create_task(telemetry_worker.start())
    yield
    # Shutdown
    telemetry_worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-grade cybersecurity backend for high-velocity telemetry ingestion, "
        "real-time credential sanitization, Isolation Forest anomaly scoring, "
        "and sub-1.5 ms vectorized cosine similarity hardware retrieval."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(telemetry_router)
app.include_router(search_router)
app.include_router(health_router)
app.include_router(demo_router)

# Mount Static Files for Live Test Studio
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", summary="Root Health & Meta Endpoint")
async def root():
    return {
        "status": "operational",
        "platform": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "documentation": "/docs",
        "live_demo_studio": "/demo",
        "prometheus_metrics": "/metrics",
    }
