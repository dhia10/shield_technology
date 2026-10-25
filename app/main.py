"""
Shield Technology Master Application Entrypoint.
Exposes FastAPI application instance for Uvicorn and test runners.
"""

import os
import sys

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.api.main import app
from app.api.routers.demo import router as demo_router
from app.api.routers.health import router as health_router
from app.api.routers.search import router as search_router
from app.api.routers.telemetry import router as telemetry_router

__all__ = ["app", "telemetry_router", "search_router", "health_router", "demo_router"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
