"""
Shield Technology Master Application Entrypoint.
Exposes FastAPI application instance for Uvicorn and test runners.
"""

from app.api.main import app
from app.api.routers.demo import router as demo_router
from app.api.routers.health import router as health_router
from app.api.routers.search import router as search_router
from app.api.routers.telemetry import router as telemetry_router

__all__ = ["app", "telemetry_router", "search_router", "health_router", "demo_router"]
