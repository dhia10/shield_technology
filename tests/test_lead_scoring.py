"""
Unit tests for Shield Technology Lead Qualification & Scoring Pipeline.
Validates multi-pillar scoring, lexical NLP urgency signals, input sanitization, and webhook triggers.
"""

import pytest
from pydantic import ValidationError

from domain.enums import (
    ClientType,
    LeadDomain,
    ProjectUrgency,
    QualificationTier,
)
import asyncio
from domain.schemas import LeadSubmitRequest


def test_high_priority_enterprise_lead(isolated_lead_scoring_service, mock_webhook_client):
    """
    An enterprise with high budget, corporate email, and mission-critical urgency
    must score Tier 1 VIP and trigger a dispatch webhook.
    """
    svc = isolated_lead_scoring_service
    req = LeadSubmitRequest(
        contact_name="Dr. Tarek Ben Amor",
        company_name="Banque Centrale / Direction IT",
        email="tarek.benamor@bct.gov.tn",  # Institutional corporate domain
        phone="+216 71 123 456",
        client_type=ClientType.OIV,
        domain_interest=LeadDomain.VIDEOSURVEILLANCE,
        project_description=(
            "Besoin urgent d'un audit de sécurité pour sécuriser notre nouveau datacenter. "
            "Risque critique de faille périmétrique et mise en conformité immédiate requise."
        ),
        urgency=ProjectUrgency.IMMEDIATE_MISSION_CRITICAL,
        surface_m2=2500.0,
        estimated_budget_tnd=45000.0,
    )

    response = asyncio.run(svc.process_and_dispatch_lead(req))

    assert response.opportunity_score >= 80.0
    assert response.qualification_tier == QualificationTier.TIER_1_ENTERPRISE_VIP
    assert response.dispatch_webhook_delivered is True
    assert len(mock_webhook_client.dispatched_events) == 1
    assert "urgent" in response.breakdown.detected_urgency_keywords
    assert "critique" in response.breakdown.detected_urgency_keywords


def test_standard_retail_lead(isolated_lead_scoring_service, mock_webhook_client):
    """
    A retail client with public email and exploratory quote should receive Tier 3 standard
    without triggering high-priority webhook.
    """
    svc = isolated_lead_scoring_service
    req = LeadSubmitRequest(
        contact_name="Mohamed",
        email="mohamed.client@gmail.com",  # Public mail provider
        phone="98765432",
        client_type=ClientType.RETAIL,
        domain_interest=LeadDomain.ALARM_INTRUSION,
        project_description="Je cherche juste un devis indicatif pour une petite boutique de quartier.",
        urgency=ProjectUrgency.EXPLORATORY_QUOTE,
        surface_m2=50.0,
        estimated_budget_tnd=800.0,
    )

    response = asyncio.run(svc.process_and_dispatch_lead(req))

    assert response.opportunity_score < 55.0
    assert response.qualification_tier in (
        QualificationTier.TIER_3_STANDARD,
        QualificationTier.UNQUALIFIED_LOW_CONFIDENCE,
    )
    # Low-tier leads should not trigger executive webhook dispatch
    assert response.dispatch_webhook_delivered is False
    assert len(mock_webhook_client.dispatched_events) == 0


def test_input_sanitization_defense():
    """Verifies that script injection tags are stripped and escaped."""
    req = LeadSubmitRequest(
        contact_name="<script>alert('xss')</script>Jean",
        company_name="<b>Corp</b>",
        email="jean@corp.com",
        phone="+216 22 111 222",
        client_type=ClientType.ENTERPRISE,
        domain_interest=LeadDomain.IT_INFRASTRUCTURE,
        project_description="Projet d'infrastructure <script>eval('malicious')</script> pour nos serveurs.",
        urgency=ProjectUrgency.PLANNED_1_MONTH,
    )

    assert "<script>" not in req.contact_name
    assert "<script>" not in req.project_description
    assert "Jean" in req.contact_name


def test_validation_errors_on_malformed_inputs():
    """Verifies strict validation on email and phone formats."""
    # Invalid email
    with pytest.raises(ValidationError):
        LeadSubmitRequest(
            contact_name="Test Name",
            email="not-an-email",
            phone="+216 22 111 222",
            client_type=ClientType.ENTERPRISE,
            domain_interest=LeadDomain.VIDEOSURVEILLANCE,
            project_description="Description longue valide pour le projet de sécurité.",
            urgency=ProjectUrgency.PLANNED_1_MONTH,
        )

    # Description too short (< 10 chars)
    with pytest.raises(ValidationError):
        LeadSubmitRequest(
            contact_name="Test Name",
            email="valid@test.com",
            phone="+216 22 111 222",
            client_type=ClientType.ENTERPRISE,
            domain_interest=LeadDomain.VIDEOSURVEILLANCE,
            project_description="Court",
            urgency=ProjectUrgency.PLANNED_1_MONTH,
        )
