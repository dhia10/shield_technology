"""
Backward-compatibility re-export module for app.models.
"""

from app.storage.models import Base, TelemetryEventModel

__all__ = ["Base", "TelemetryEventModel"]
