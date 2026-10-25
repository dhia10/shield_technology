"""
7-Dimensional Feature Extraction Engine for Security Telemetry.
Computes mathematical metrics: Shannon entropy H(X), payload size, keyword density,
network classification, and IP entropy for machine learning threat scoring.
"""

from collections import Counter
import json
import math
from typing import Any, Dict, List, Union
import numpy as np

from app.schemas.enums import EventTypeEnum
from app.schemas.telemetry import SanitizedTelemetryEvent

SUSPICIOUS_KEYWORDS = [
    "select", "union", "drop", "insert", "delete", "where", "1=1", "--",
    "password", "secret", "token", "eval", "exec", "system", "cmd",
    "powershell", "/bin/sh", "/bin/bash", "../", "..\\", "chmod", "curl", "wget", "syn"
]


def calculate_shannon_entropy(text: str) -> float:
    """Calculates the Shannon entropy H(X) = -sum(p * log2(p)) of a string."""
    if not text:
        return 0.0
    length = len(text)
    counts = Counter(text)
    entropy = -sum((count / length) * math.log2(count / length) for count in counts.values())
    return round(entropy, 4)


class FeatureExtractor7D:
    """
    Extracts 7-dimensional normalized feature vector from raw/sanitized telemetry:
    1. shannon_entropy: Information entropy of payload string (0 to 8 bits)
    2. payload_length: Byte length normalized to KB
    3. key_count: Count of root keys in JSON payload
    4. is_external_wan: 1.0 if incoming from public WAN, 0.0 if LAN/loopback
    5. threat_event_type: Heuristic severity weight (1.0 for exploits/floods, 0.5 scans, 0.0 metrics)
    6. suspicious_keyword_density: Ratio of exploit keywords to total words
    7. ip_octet_entropy: Shannon entropy of the source IP string
    """

    FEATURE_NAMES: List[str] = [
        "shannon_entropy",
        "payload_length",
        "key_count",
        "is_external_wan",
        "threat_event_type",
        "suspicious_keyword_density",
        "ip_octet_entropy",
    ]

    @classmethod
    def extract_vector(cls, event_data: Union[SanitizedTelemetryEvent, Dict[str, Any]]) -> np.ndarray:
        metrics = cls.extract_dict(event_data)
        return np.array([metrics[name] for name in cls.FEATURE_NAMES], dtype=np.float32)

    @classmethod
    def extract_dict(cls, event_data: Union[SanitizedTelemetryEvent, Dict[str, Any]]) -> Dict[str, float]:
        if isinstance(event_data, SanitizedTelemetryEvent):
            payload = event_data.sanitized_payload or {}
            event_type = event_data.event_type.value if hasattr(event_data.event_type, "value") else str(event_data.event_type)
            source_ip = event_data.source_ip or ""
            enrichment = event_data.enrichment or {}
        else:
            payload = event_data.get("sanitized_payload") or event_data.get("payload") or {}
            event_type = str(event_data.get("event_type", ""))
            source_ip = str(event_data.get("source_ip", ""))
            enrichment = event_data.get("enrichment") or {}

        payload_str = json.dumps(payload, default=str).lower()
        entropy = calculate_shannon_entropy(payload_str)
        payload_len = min(len(payload_str), 10000) / 1000.0  # KB
        key_count = float(len(payload.keys()))

        network_class = enrichment.get("network_class", "")
        is_external = 1.0 if network_class == "EXTERNAL_WAN" else 0.0

        is_threat = 1.0 if event_type in [
            "SQL_INJECTION_ATTEMPT", "DDOS_SYN_FLOOD", "DDOS_FLOOD", "MALWARE_DETECTED", "SSH_BRUTE_FORCE"
        ] else (0.5 if event_type in ["PORT_SCAN", "AUTH_ATTEMPT", "ANOMALOUS_PAYLOAD"] else 0.0)

        # Keyword density
        words = payload_str.replace("{", " ").replace("}", " ").replace(":", " ").replace(",", " ").split()
        kw_hits = sum(1 for kw in SUSPICIOUS_KEYWORDS if kw in payload_str)
        kw_density = round(kw_hits / max(1, len(words)), 4)

        # IP entropy
        ip_entropy = calculate_shannon_entropy(source_ip)

        return {
            "shannon_entropy": float(entropy),
            "payload_length": float(round(payload_len, 4)),
            "key_count": float(key_count),
            "is_external_wan": float(is_external),
            "threat_event_type": float(is_threat),
            "suspicious_keyword_density": float(kw_density),
            "ip_octet_entropy": float(ip_entropy),
        }
