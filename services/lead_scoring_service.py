"""
Shield Technology Lead Qualification & Scoring Pipeline.
Implements a deterministic multi-factor scoring engine (0-100) evaluating:
1. Contact completeness & corporate integrity
2. Lexical NLP urgency detection
3. Economic scale and infrastructure footprint
4. Automated webhook dispatch to n8n / CRM for high-tier opportunities.
"""

from datetime import datetime, timezone
import logging
import re
from typing import List, Optional, Set

from domain.entities import LeadEntity
from domain.enums import (
    ClientType,
    ProjectUrgency,
    QualificationTier,
)
from domain.schemas import (
    LeadScoringBreakdown,
    LeadSubmitRequest,
    LeadSubmitResponse,
)
from infrastructure.webhook_client import HttpWebhookClient, WebhookClientInterface

logger = logging.getLogger("shield.lead_scoring")

FREE_MAIL_PROVIDERS: Set[str] = {
    "gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr",
    "outlook.com", "outlook.fr", "live.com", "icloud.com", "mail.ru", "proton.me",
}

URGENCY_KEYWORDS: List[str] = [
    "urgent", "urgence", "panne", "immédiat", "intrusion", "sinistre",
    "conformité", "audit", "dépannage", "astreinte", "vol", "contrat",
    "appel d'offres", "ao", "sécurisation", "faille", "critique",
]

SQLI_XSS_PATTERNS = re.compile(
    r"(union\s+select|drop\s+table|exec\(|<script|javascript:|alert\()",
    re.IGNORECASE,
)


class LeadScoringService:
    """Evaluates commercial inquiries and orchestrates qualified leads dispatch."""

    def __init__(self, webhook_client: Optional[WebhookClientInterface] = None):
        self.webhook_client = webhook_client or HttpWebhookClient()

    def _detect_urgency_keywords(self, text: str) -> List[str]:
        """Scans project description for high-priority lexical markers."""
        lower = text.lower()
        found = []
        for kw in URGENCY_KEYWORDS:
            if kw in lower:
                found.append(kw)
        return found

    def _is_corporate_email(self, email: str) -> bool:
        """Determines if the email belongs to a corporate or institutional domain."""
        try:
            domain = email.split("@")[1].lower()
            return domain not in FREE_MAIL_PROVIDERS
        except Exception:
            return False

    def evaluate_lead(self, request: LeadSubmitRequest) -> LeadScoringBreakdown:
        """
        Executes deterministic multi-pillar scoring rubric (0 - 100).
        Guarantees explainable, audited scoring factors.
        """
        # 1. Contact & Submission Completeness (Max 30 pts)
        completeness = 0.0
        if len(request.contact_name.strip()) >= 3:
            completeness += 5.0
        if request.company_name and len(request.company_name.strip()) >= 2:
            completeness += 5.0
        if request.phone and len(request.phone.strip()) >= 8:
            completeness += 5.0
        if request.surface_m2 and request.surface_m2 > 0:
            completeness += 5.0
        if request.estimated_budget_tnd and request.estimated_budget_tnd > 0:
            completeness += 5.0
        if len(request.project_description.strip()) >= 40:
            completeness += 5.0

        # 2. Urgency & NLP Keywords (Max 25 pts)
        urgency_points = 0.0
        if request.urgency == ProjectUrgency.IMMEDIATE_MISSION_CRITICAL:
            urgency_points += 15.0
        elif request.urgency == ProjectUrgency.URGENT_1_WEEK:
            urgency_points += 10.0
        elif request.urgency == ProjectUrgency.PLANNED_1_MONTH:
            urgency_points += 5.0
        else:
            urgency_points += 2.0

        detected_kw = self._detect_urgency_keywords(request.project_description)
        urgency_points += min(10.0, len(detected_kw) * 2.5)

        # 3. Scale, Client Type & Budget Weight (Max 25 pts)
        scale_points = 0.0
        if request.client_type in (ClientType.GOVERNMENT, ClientType.OIV):
            scale_points += 15.0
        elif request.client_type in (ClientType.ENTERPRISE, ClientType.INDUSTRY):
            scale_points += 12.0
        elif request.client_type == ClientType.RESIDENTIAL_VIP:
            scale_points += 8.0
        else:
            scale_points += 5.0

        # Budget & Surface weight
        budget = request.estimated_budget_tnd or 0.0
        surface = request.surface_m2 or 0.0
        if budget >= 20000.0 or surface >= 2000.0:
            scale_points += 10.0
        elif budget >= 5000.0 or surface >= 500.0:
            scale_points += 6.0
        elif budget >= 1000.0 or surface >= 100.0:
            scale_points += 3.0

        # 4. Corporate Domain Bonus (Max 20 pts)
        if self._is_corporate_email(request.email):
            corp_bonus = 20.0
        else:
            corp_bonus = 5.0

        # Composite Score Calculation
        total = round(min(100.0, completeness + urgency_points + scale_points + corp_bonus), 1)

        # Tier classification
        if total >= 75.0:
            tier = QualificationTier.TIER_1_ENTERPRISE_VIP
            action = "Appel téléphonique prioritaire sous 30 minutes par un Ingénieur Senior."
        elif total >= 55.0:
            tier = QualificationTier.TIER_2_QUALIFIED
            action = "Traitement commercial prioritaire avec devis estimatif sous 24h."
        elif total >= 35.0:
            tier = QualificationTier.TIER_3_STANDARD
            action = "Envoi automatique de documentation technique et prise de contact standard."
        else:
            tier = QualificationTier.UNQUALIFIED_LOW_CONFIDENCE
            action = "Demande d'informations complémentaires par email pour affiner le besoin."

        return LeadScoringBreakdown(
            completeness_score=completeness,
            urgency_score=urgency_points,
            scale_budget_score=scale_points,
            corporate_domain_bonus=corp_bonus,
            final_opportunity_score=total,
            qualification_tier=tier,
            detected_urgency_keywords=detected_kw,
            action_recommendation=action,
        )

    async def process_and_dispatch_lead(self, request: LeadSubmitRequest) -> LeadSubmitResponse:
        """Evaluates incoming lead and delivers webhook notification if qualified."""
        breakdown = self.evaluate_lead(request)
        lead_id = f"lead_{int(datetime.now(timezone.utc).timestamp())}_{abs(hash(request.email)) % 10000}"

        delivered = False
        # Dispatch notification if qualified (Tier 1 or Tier 2)
        if breakdown.qualification_tier in (
            QualificationTier.TIER_1_ENTERPRISE_VIP,
            QualificationTier.TIER_2_QUALIFIED,
        ):
            payload = {
                "lead_id": lead_id,
                "contact_name": request.contact_name,
                "company_name": request.company_name,
                "email": request.email,
                "phone": request.phone,
                "client_type": request.client_type.value,
                "domain_interest": request.domain_interest.value,
                "urgency": request.urgency.value,
                "opportunity_score": breakdown.final_opportunity_score,
                "qualification_tier": breakdown.qualification_tier.value,
                "project_description": request.project_description,
                "action_recommendation": breakdown.action_recommendation,
                "detected_urgency_keywords": breakdown.detected_urgency_keywords,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
            delivered = await self.webhook_client.dispatch(payload, event_name="lead.qualified")

        return LeadSubmitResponse(
            lead_id=lead_id,
            status="qualified" if breakdown.final_opportunity_score >= 55.0 else "received",
            opportunity_score=breakdown.final_opportunity_score,
            qualification_tier=breakdown.qualification_tier,
            breakdown=breakdown,
            dispatch_webhook_delivered=delivered,
            created_at=datetime.now(timezone.utc),
        )


# Global singleton instance
lead_scoring_service = LeadScoringService()
