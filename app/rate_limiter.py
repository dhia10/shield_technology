"""
Backward-compatibility re-export module for app.rate_limiter.
"""

from app.security.rate_limiter import (
    SlidingWindowRateLimiter,
    agent_rate_limiter,
    check_rate_limit,
)

__all__ = ["SlidingWindowRateLimiter", "agent_rate_limiter", "check_rate_limit"]
