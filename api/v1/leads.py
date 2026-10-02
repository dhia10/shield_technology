"""
Shield Technology Lead Qualification API Controller.
RFQ evaluation, deterministic opportunity scoring, and automated orchestration dispatch.
"""

from fastapi import APIRouter, status
from domain.schemas import LeadSubmitRequest, LeadSubmitResponse
from services.lead_scoring_service import lead_scoring_service

router = APIRouter(prefix="/leads", tags=["Lead Qualification & Scoring Pipeline"])


@router.post(
    "/qualify",
    response_model=LeadSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate, Score and Orchestrate Lead Submission",
    description="Calculates composite opportunity score (0-100) and dispatches webhook for high-tier leads.",
)
async def qualify_and_submit_lead(request: LeadSubmitRequest) -> LeadSubmitResponse:
    return await lead_scoring_service.process_and_dispatch_lead(request)


@router.get(
    "/rubric",
    summary="Transparent Scoring Criteria Specification",
)
async def get_scoring_rubric():
    return {
        "max_score": 100,
        "pillars": {
            "completeness_and_contact": {"max_points": 30, "description": "Form integrity, phone validity, surface, budget, and description length"},
            "urgency_and_nlp_keywords": {"max_points": 25, "description": "Criticality tier and lexical detection of mission-critical terms"},
            "scale_and_client_type": {"max_points": 25, "description": "Government, OIV, Enterprise scale vs standard retail"},
            "corporate_domain_bonus": {"max_points": 20, "description": "Verified business/institutional domain vs free public mail providers"},
        },
        "tiers": {
            "TIER_1_ENTERPRISE_VIP": {"min_score": 75, "sla_response": "30 minutes phone callback"},
            "TIER_2_QUALIFIED": {"min_score": 55, "sla_response": "24 hours formal quotation"},
            "TIER_3_STANDARD": {"min_score": 35, "sla_response": "Standard technical catalog dispatch"},
            "UNQUALIFIED_LOW_CONFIDENCE": {"min_score": 0, "sla_response": "Automated clarification request"},
        },
    }
