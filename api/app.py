"""
Shield Technology Data & AI Platform - FastAPI Application Entrypoint.
Exposes OpenAPI 3.1 documentation, health metrics, and v1 REST controllers.
"""

from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.telemetry import router as telemetry_router
from api.v1.search import router as search_router
from api.v1.leads import router as leads_router
from infrastructure.config import settings
from services.search_service import search_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown hooks."""
    # Auto-seed mock data if vector store is unpopulated
    if search_service.count_indexed() == 0:
        try:
            from scripts.seed_demo_data import seed_catalog_data
            seed_catalog_data(search_service)
        except Exception as exc:
            pass
    yield
    # Shutdown flushes remaining telemetry buffer
    try:
        from services.telemetry_service import telemetry_service
        telemetry_service.flush()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-grade, clean-architecture Data & AI backend for Shield Technology. "
        "Encompasses proprietary telemetry ingestion, dense semantic vector retrieval, "
        "and automated lead scoring."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_and_security_headers(request: Request, call_next):
    """Attaches latency instrumentation and defense headers."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# Include Version 1 Routers
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(leads_router, prefix="/api/v1")


@app.get("/", tags=["System"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "documentation": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
        "indexed_catalog_size": search_service.count_indexed(),
    }
