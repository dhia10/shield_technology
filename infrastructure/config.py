"""
Shield Technology Configuration Management.
Zero-secret architecture adhering to 12-Factor App principles.
Loads from environment variables and .env with sensible defaults for local development.
"""

import os
from typing import List
from pydantic import BaseModel, Field


def _load_env_file(filepath: str = ".env") -> None:
    """Lightweight .env parser that sets os.environ without requiring external packages."""
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_env_file()


class AppSettings(BaseModel):
    """Immutable application settings validated at boot."""

    APP_NAME: str = os.getenv("APP_NAME", "Shield Technology Data & AI Platform")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: List[str] = [
        "https://shieldtechnology.tn",
        "https://www.shieldtechnology.tn",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ]

    # Telemetry Ingestion configuration
    TELEMETRY_BUFFER_CAPACITY: int = int(os.getenv("TELEMETRY_BUFFER_CAPACITY", "1000"))
    TELEMETRY_BATCH_FLUSH_SIZE: int = int(os.getenv("TELEMETRY_BATCH_FLUSH_SIZE", "50"))
    TELEMETRY_FLUSH_INTERVAL_SECONDS: float = float(os.getenv("TELEMETRY_FLUSH_INTERVAL_SECONDS", "5.0"))

    # Semantic Search & Embeddings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    VECTOR_DIMENSION: int = int(os.getenv("VECTOR_DIMENSION", "384"))
    DEFAULT_CONFIDENCE_THRESHOLD: float = float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.25"))

    # Storage paths
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "data/shield_telemetry.db")

    # External Webhooks (n8n / CRM) - Zero secrets committed
    N8N_DISPATCH_WEBHOOK_URL: str = os.getenv("N8N_DISPATCH_WEBHOOK_URL", "")
    WEBHOOK_SIGNING_SECRET: str = os.getenv("WEBHOOK_SIGNING_SECRET", "")
    WEBHOOK_TIMEOUT_SECONDS: float = float(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "4.0"))
    MOCK_WEBHOOKS: bool = os.getenv("MOCK_WEBHOOKS", "true").lower() in ("true", "1", "yes")


# Global cached settings instance
settings = AppSettings()
