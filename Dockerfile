# ==============================================================================
# Shield Technology Telemetry & Intelligence Platform
# Production Multi-Stage Hardened Container Image (Python 3.11-slim)
# ==============================================================================

# Stage 1: Build stage
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/appuser/.local/bin:$PATH

# Create non-root application user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application sources
COPY --chown=appuser:appgroup app/ /app/app/
COPY --chown=appuser:appgroup scripts/ /app/scripts/
COPY --chown=appuser:appgroup static/ /app/static/
COPY --chown=appuser:appgroup pyproject.toml /app/

# Persistent directory for local SQLite / archive backups
RUN mkdir -p /app/data /app/archives && chown -R appuser:appgroup /app/data /app/archives

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
