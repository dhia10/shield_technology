"""
Sensitive Data Masking and Sanitization Engine.
Recursively sanitizes passwords, auth tokens, JWTs, and API credentials to '***REDACTED***'.
"""

import copy
import re
from typing import Any, Dict, List, Set, Union

SENSITIVE_KEYS: Set[str] = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "private_key",
    "credit_card",
    "card_number",
    "cvv",
    "pin",
    "bearer",
    "jwt",
}

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
REDACTED_STR = "***REDACTED***"


class SensitiveDataSanitizer:
    """Enterprise secret scrubber enforcing Zero-Cleartext-Credential ingestion."""

    @classmethod
    def sanitize(cls, data: Any) -> Any:
        """
        Recursively traverses nested dictionaries, lists, and strings to redact secrets.
        """
        if isinstance(data, dict):
            sanitized: Dict[str, Any] = {}
            for k, v in data.items():
                lower_key = str(k).lower().strip()
                if any(sensitive in lower_key for sensitive in SENSITIVE_KEYS):
                    sanitized[k] = REDACTED_STR
                else:
                    sanitized[k] = cls.sanitize(v)
            return sanitized

        elif isinstance(data, list):
            return [cls.sanitize(item) for item in data]

        elif isinstance(data, str):
            masked = JWT_PATTERN.sub(REDACTED_STR, data)
            masked = CREDIT_CARD_PATTERN.sub(REDACTED_STR, masked)
            return masked

        return data
