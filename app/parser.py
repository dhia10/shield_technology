"""
Backward-compatibility re-export module for app.parser.
"""

from app.ingestion.enricher import EventHasher, IPEnricher
from app.ingestion.parser import LogParser, MalformedLogException
from app.ingestion.sanitizer import REDACTED_STR, SensitiveDataSanitizer

__all__ = [
    "LogParser",
    "MalformedLogException",
    "SensitiveDataSanitizer",
    "IPEnricher",
    "EventHasher",
    "REDACTED_STR",
]
