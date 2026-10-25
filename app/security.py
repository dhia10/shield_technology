"""
Backward-compatibility re-export module for app.security.
"""

from app.security.auth import (
    API_KEY,
    HMAC_SECRET,
    compute_hmac_signature,
    verify_probe_auth,
)

__all__ = [
    "API_KEY",
    "HMAC_SECRET",
    "compute_hmac_signature",
    "verify_probe_auth",
]
