"""
Backward-compatibility re-export module for app.schemas.
"""

from app.schemas.enums import (
    ClientType,
    EquipmentCategory,
    EventTypeEnum,
    LeadDomain,
    ProjectUrgency,
    QualificationTier,
    SeverityEnum,
)
from app.schemas.search import (
    RecommendationRequest,
    RecommendationResponse,
    SearchResultItem,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.schemas.telemetry import (
    RawTelemetryEvent,
    SanitizedTelemetryEvent,
    TelemetryHistoryResponse,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryStatsResponse,
)

# Alias for backward compatibility with existing tests
TelemetryHistoryItem = SanitizedTelemetryEvent

__all__ = [
    "SeverityEnum",
    "EventTypeEnum",
    "EquipmentCategory",
    "QualificationTier",
    "ClientType",
    "LeadDomain",
    "ProjectUrgency",
    "RawTelemetryEvent",
    "SanitizedTelemetryEvent",
    "TelemetryHistoryItem",
    "TelemetryIngestRequest",
    "TelemetryIngestResponse",
    "TelemetryHistoryResponse",
    "TelemetryStatsResponse",
    "SearchResultItem",
    "SemanticSearchRequest",
    "SemanticSearchResponse",
    "RecommendationRequest",
    "RecommendationResponse",
]
