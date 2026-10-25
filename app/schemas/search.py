"""
Pydantic Schemas for Vector Search and Equipment Recommendations.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import EquipmentCategory


class SearchResultItem(BaseModel):
    """Retrieved hardware item with relevance score."""
    id: str
    slug: str
    name: str
    category: EquipmentCategory
    manufacturer: str
    description: str
    technical_specs: Dict[str, Any] = Field(default_factory=dict)
    certifications: List[str] = Field(default_factory=list)
    warranty_months: int = 24
    price_tnd: float = 0.0
    in_stock: bool = True
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    match_confidence_tier: str = "Medium"

    model_config = ConfigDict(extra="ignore")


class SemanticSearchRequest(BaseModel):
    """Natural language query payload."""
    query: str = Field(..., min_length=2, max_length=500, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=20)
    min_confidence: float = Field(default=0.10, ge=0.0, le=1.0)
    category: Optional[EquipmentCategory] = None


class SemanticSearchResponse(BaseModel):
    """Search results with execution timing."""
    query: str
    total_matches: int
    execution_time_ms: float
    results: List[SearchResultItem]


class RecommendationRequest(BaseModel):
    """Request for cross-category complementary hardware."""
    source_item_id: str = Field(..., description="Source equipment ID to recommend pairings for")
    max_recommendations: int = Field(default=3, ge=1, le=10)


class RecommendationResponse(BaseModel):
    """Contextual recommendations for cross-sell and technical completeness."""
    source_item_id: str
    recommendations: List[SearchResultItem]
