"""
Shield Technology - Security & Authentication Layer
Weeks 5 & 9: Probe validation via X-API-Key and cryptographic HMAC-SHA256 signature verification.
"""

import hmac
import hashlib
import os
from typing import Optional
from fastapi import Header, HTTPException, Request, status

API_KEY = os.getenv("TELEMETRY_API_KEY", "shield_probe_secret_key_2026")
HMAC_SECRET = os.getenv("HMAC_SECRET_KEY", "shield_hmac_master_secret_tunisia_2026")


def compute_hmac_signature(body_bytes: bytes, secret: str = HMAC_SECRET) -> str:
    """Computes HMAC-SHA256 hex digest for request integrity verification."""
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


async def verify_probe_auth(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_hmac_signature: Optional[str] = Header(None, alias="X-HMAC-Signature"),
):
    """
    FastAPI Dependency to authenticate probes and verify payload integrity.
    Rejects requests with missing/invalid API keys or tampered signatures.
    """
    # 1. API Key verification
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )

    # 2. HMAC Signature verification
    raw_body = await request.body()
    if not raw_body:
        return True

    if not x_hmac_signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-HMAC-Signature header for payload integrity",
        )

    expected_signature = compute_hmac_signature(raw_body, HMAC_SECRET)
    if not hmac.compare_digest(expected_signature, x_hmac_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cryptographic HMAC signature mismatch. Payload may have been tampered with.",
        )

    return True
