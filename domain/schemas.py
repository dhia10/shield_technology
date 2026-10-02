"""
Shield Technology Pydantic DTOs & Validation Schemas.
Enforces static contracts and validation across HTTP boundaries (Zero "Vibe Coding").
"""

from datetime import datetime
import html
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from domain.enums import (
    ClientType,
    EquipmentCategory,
    EventType,
    LeadDomain,
    ProjectUrgency,
    QualificationTier,
)

# Common regex patterns
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-\.()]{6,20}$")
DANGEROUS_HTML_TAGS = re.compile(r"<[^>]*?>")


def sanitize_text(text: str) -> str:
    """Strips HTML tags and escapes dangerous scripting characters."""
    stripped = DANGEROUS_HTML_TAGS.sub("", text)
    escaped = html.escape(stripped)
    return escaped.strip()


# ─── Telemetry Schemas ────────────────────────────────────────────────────────

class TelemetryEventCreate(BaseModel):
    """Payload for capturing an individual client telemetry event."""
    event_type: EventType = Field(..., description="Action/metric category")
    session_id: str = Field(..., min_length=4, max_length=128, description="Client session identifier")
    page_path: str = Field(..., min_length=1, max_length=512, description="Target URL path")
    element_id: Optional[str] = Field(None, max_length=128, description="Target DOM selector or button name")
    duration_seconds: Optional[float] = Field(None, ge=0.0, le=86400.0, description="Dwell time or action latency")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary event dimensions")

    @field_validator("page_path", "element_id")
    @classmethod
    def clean_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_text(v)
        return v


class TelemetryBatchCreate(BaseModel):
    """Batch payload for high-throughput non-blocking telemetry ingestion."""
    events: List[TelemetryEventCreate] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="List of telemetry events to ingest in batch",
    )


class TelemetryIngestResponse(BaseModel):
    """Acknowledgement response returned to client."""
    status: str = Field(default="accepted")
    count: int = Field(..., description="Number of events accepted into buffer")
    buffer_utilization_pct: float = Field(..., description="Current memory queue occupancy")


class TelemetryMetricsResponse(BaseModel):
    """Observability metrics for the telemetry ingestion pipeline."""
    total_events_received: int
    total_batches_flushed: int
    current_buffer_size: int
    buffer_capacity: int
    error_count: int
    events_by_type: Dict[str, int]
    hourly_throughput_estimate: float
    uptime_seconds: float


# ─── Semantic Search & Recommendation Schemas ─────────────────────────────────

class SemanticSearchRequest(BaseModel):
    """Query payload for semantic similarity search."""
    query: str = Field(..., min_length=2, max_length=300, description="Natural language security inquiry")
    category: Optional[EquipmentCategory] = Field(None, description="Optional category filter")
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum items to return")
    min_confidence: float = Field(
        default=0.25, ge=0.0, le=1.0, description="Cosine similarity threshold"
    )

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        return sanitize_text(v)


class SearchResultItem(BaseModel):
    """Item descriptor returned from semantic vector retrieval."""
    id: str
    slug: str
    name: str
    category: EquipmentCategory
    manufacturer: str
    description: str
    technical_specs: Dict[str, Any]
    certifications: List[str]
    warranty_months: int
    price_tnd: float
    in_stock: bool
    similarity_score: float = Field(..., description="Cosine similarity [0.0 - 1.0]")
    match_confidence_tier: str = Field(..., description="High, Medium, Low confidence")


class SemanticSearchResponse(BaseModel):
    """Complete semantic search response payload."""
    query: str
    total_matches: int
    execution_time_ms: float
    results: List[SearchResultItem]


class RecommendationRequest(BaseModel):
    """Request for complementary security hardware / SLA services."""
    source_item_id: str = Field(..., description="Target equipment ID")
    max_recommendations: int = Field(default=3, ge=1, le=10)


class RecommendationResponse(BaseModel):
    """Contextual recommendations for cross-sell and technical completeness."""
    source_item_id: str
    recommendations: List[SearchResultItem]


# ─── Lead Qualification & Opportunity Scoring Schemas ─────────────────────────

class LeadSubmitRequest(BaseModel):
    """Commercial / technical RFQ submission."""
    contact_name: str = Field(..., min_length=2, max_length=100)
    company_name: Optional[str] = Field(None, max_length=150)
    email: str = Field(..., min_length=5, max_length=150)
    phone: str = Field(..., min_length=6, max_length=30)
    client_type: ClientType
    domain_interest: LeadDomain
    project_description: str = Field(..., min_length=10, max_length=2000)
    urgency: ProjectUrgency
    surface_m2: Optional[float] = Field(None, ge=1.0, le=500000.0)
    estimated_budget_tnd: Optional[float] = Field(None, ge=100.0, le=5000000.0)

    @field_validator("contact_name", "company_name", "project_description")
    @classmethod
    def sanitize_inputs(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return sanitize_text(v)
        return v

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Format d'adresse email invalide")
        return clean

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = v.strip()
        if not PHONE_REGEX.match(clean):
            raise ValueError("Format de numéro de téléphone invalide")
        return clean


class LeadScoringBreakdown(BaseModel):
    """Transparent rubric detailing opportunity calculation."""
    completeness_score: float = Field(..., description="Points from contact completeness (max 30)")
    urgency_score: float = Field(..., description="Points from urgency level & keywords (max 25)")
    scale_budget_score: float = Field(..., description="Points from surface/budget/tier (max 25)")
    corporate_domain_bonus: float = Field(..., description="Bonus for custom enterprise email (max 20)")
    final_opportunity_score: float = Field(..., ge=0.0, le=100.0, description="Composite score (0-100)")
    qualification_tier: QualificationTier
    detected_urgency_keywords: List[str]
    action_recommendation: str


class LeadSubmitResponse(BaseModel):
    """Response returned upon lead evaluation and ingestion."""
    lead_id: str
    status: str
    opportunity_score: float
    qualification_tier: QualificationTier
    breakdown: LeadScoringBreakdown
    dispatch_webhook_delivered: bool
    created_at: datetime
