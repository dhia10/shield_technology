"""
Backward-compatibility re-export module for app.cache.
"""

from app.storage.cache import CacheService, cache_service

__all__ = ["CacheService", "cache_service"]
