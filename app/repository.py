"""
Backward-compatibility re-export module for app.repository.
"""

from app.storage.repository import TelemetryRepository

__all__ = ["TelemetryRepository"]
