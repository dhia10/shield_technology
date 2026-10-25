"""
Shield Technology Core Configuration Module.
Adheres to 12-factor application design, loading settings from environment variables
with validated defaults for local testing, staging, and high-security production.
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


class Settings(BaseModel):
    """Immutable application settings validated at boot."""

    APP_NAME: str = os.getenv("APP_NAME", "Shield Technology - Security Telemetry & AI Platform")
    APP_VERSION: str = os.getenv("APP_VERSION", "2.5.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Network & API
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: List[str] = [
        "https://shieldtechnology.tn",
        "https://www.shieldtechnology.tn",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # Security Credentials
    API_KEY: str = os.getenv("SHIELD_API_KEY", "shield_probe_secret_key_2026")
    HMAC_SECRET: str = os.getenv("SHIELD_HMAC_SECRET", "super_secret_hmac_sha256_key_for_telemetry_2026")
    API_KEY_HEADER: str = "X-API-Key"
    HMAC_SIGNATURE_HEADER: str = "X-HMAC-Signature"

    # Rate Limiting & Buffer
    RATE_LIMIT_RPS: int = int(os.getenv("RATE_LIMIT_RPS", "1000"))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "2000"))
    RING_BUFFER_CAPACITY: int = int(os.getenv("RING_BUFFER_CAPACITY", "50000"))

    # Database & Storage
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./data/shield_telemetry_async.db"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    ARCHIVE_DIR: str = os.getenv("ARCHIVE_DIR", "./data/archives")

    # ML Anomaly Detection & Threat Scoring
    ML_CONTAMINATION: float = float(os.getenv("ML_CONTAMINATION", "0.12"))
    ML_ESCALATION_THRESHOLD: float = float(os.getenv("ML_ESCALATION_THRESHOLD", "0.80"))
    VECTOR_DIMENSION: int = int(os.getenv("VECTOR_DIMENSION", "384"))


settings = Settings()
