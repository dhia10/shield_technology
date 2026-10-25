"""
Backward-compatibility re-export module for app.worker.
"""

from app.workers.worker import TelemetryWorker, telemetry_worker

__all__ = ["TelemetryWorker", "telemetry_worker"]
