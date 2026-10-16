"""
Shield Technology - Caching Layer
Weeks 7-8: Redis caching for hourly/daily security aggregations with TTL and invalidation routines.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("shield.cache")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class CacheService:
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client = None
        self._memory_store = {}
        self._memory_expiry = {}

    async def connect(self):
        try:
            import redis.asyncio as aioredis
            self.client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.15,
                socket_timeout=0.15,
            )
            await asyncio.wait_for(self.client.ping(), timeout=0.2)
            logger.info("Connected to Redis cache.")
        except Exception as e:
            logger.info(f"Redis unavailable ({e}). Using in-memory fallback cache.")
            self.client = None

    async def get(self, key: str) -> Optional[Any]:
        if self.client:
            try:
                val = await self.client.get(key)
                return json.loads(val) if val else None
            except Exception:
                pass

        # In-memory fallback
        import time
        if key in self._memory_store:
            expiry = self._memory_expiry.get(key, 0)
            if expiry == 0 or expiry > time.time():
                return self._memory_store[key]
            else:
                del self._memory_store[key]
                del self._memory_expiry[key]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        serialized = json.dumps(value, default=str)
        if self.client:
            try:
                await self.client.set(key, serialized, ex=ttl_seconds)
                return True
            except Exception:
                pass

        # In-memory fallback
        import time
        self._memory_store[key] = value
        self._memory_expiry[key] = time.time() + ttl_seconds
        return True

    async def invalidate(self, key_prefix: str = "stats:") -> int:
        count = 0
        if self.client:
            try:
                keys = await self.client.keys(f"{key_prefix}*")
                if keys:
                    count = await self.client.delete(*keys)
                    return count
            except Exception:
                pass

        # In-memory fallback
        keys_to_del = [k for k in self._memory_store.keys() if k.startswith(key_prefix)]
        for k in keys_to_del:
            del self._memory_store[k]
            if k in self._memory_expiry:
                del self._memory_expiry[k]
            count += 1
        return count


cache_service = CacheService()
