"""
Shield Technology Domain Entities.
Framework-agnostic business objects encapsulating state and business invariants.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from domain.enums import (
    ClientType,
    EquipmentCategory,
    EventType,
    LeadDomain,
    ProjectUrgency,
    QualificationTier,
)


@dataclass(frozen=True)
class EquipmentEntity:
    """Represents high-reliability physical equipment or managed SLA service."""
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
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_searchable_text(self) -> str:
        """Constructs canonical text representation for semantic vectorization."""
        specs_str = " ".join(f"{k}: {v}" for k, v in self.technical_specs.items())
        certs_str = " ".join(self.certifications)
        return (
            f"Nom: {self.name}. "
            f"Fabricant: {self.manufacturer}. "
            f"Catégorie: {self.category.value}. "
            f"Description: {self.description}. "
            f"Spécifications: {specs_str}. "
            f"Certifications: {certs_str}. "
            f"Garantie: {self.warranty_months} mois."
        )


@dataclass(frozen=True)
class TelemetryEventEntity:
    """Represents an anonymized behavioral user interaction event (Zero-PII)."""
    event_type: EventType
    session_id: str
    page_path: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    element_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    user_agent: Optional[str] = None
    ip_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class LeadEntity:
    """Represents a qualified commercial or technical inquiry."""
    contact_name: str
    email: str
    phone: str
    client_type: ClientType
    domain_interest: LeadDomain
    project_description: str
    urgency: ProjectUrgency
    lead_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_name: Optional[str] = None
    surface_m2: Optional[float] = None
    estimated_budget_tnd: Optional[float] = None
    opportunity_score: float = 0.0
    qualification_tier: QualificationTier = QualificationTier.UNQUALIFIED_LOW_CONFIDENCE
    scoring_factors: Dict[str, float] = field(default_factory=dict)
    detected_keywords: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
