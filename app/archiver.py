"""
Backward-compatibility re-export module for app.archiver.
"""

from app.storage.archiver import LogArchiver, log_archiver

__all__ = ["LogArchiver", "log_archiver"]
