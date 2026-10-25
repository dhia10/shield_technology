"""
Shield Technology Rate Limiting Middleware.
Sliding window rate limiting per agent ID or client IP address.
"""

import time
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        if identifier not in self._history:
            self._history[identifier] = []

        # Filter out timestamps outside window
        self._history[identifier] = [ts for ts in self._history[identifier] if ts > cutoff]

        if len(self._history[identifier]) >= self.max_requests:
            return False

        self._history[identifier].append(now)
        return True

    def reset(self) -> None:
        self._history.clear()


# Default instance: 120 requests / minute per agent
agent_rate_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60)


async def check_rate_limit(request: Request) -> bool:
    """FastAPI Dependency for endpoints requiring per-agent or per-IP throttling."""
    client_ip = request.client.host if request.client else "unknown_host"
    agent_id = request.headers.get("X-Agent-ID", client_ip)

    if not agent_rate_limiter.is_allowed(agent_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for agent '{agent_id}'. Maximum 120 requests/minute allowed.",
            headers={"Retry-After": "60"},
        )
    return True
