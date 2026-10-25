"""
Backward-compatibility re-export module for app.ml_scorer.
"""

from app.ml.feature_extractor import FeatureExtractor7D, calculate_shannon_entropy
from app.ml.scorer import MLAnomalyScorer, ml_anomaly_scorer

__all__ = [
    "calculate_shannon_entropy",
    "FeatureExtractor7D",
    "MLAnomalyScorer",
    "ml_anomaly_scorer",
]
