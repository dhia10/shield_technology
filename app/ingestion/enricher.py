"""
Network Classification and Cryptographic Event Fingerprinting.
Classifies LAN/WAN boundaries, country geolocation tags, and deterministic event hashes.
"""

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


class IPEnricher:
    """Classifies IP address metadata, subnet tier, and geographical origin."""

    @staticmethod
    def enrich(ip_str: str) -> Dict[str, Any]:
        enrichment = {
            "is_private": False,
            "is_loopback": False,
            "network_class": "PUBLIC_INTERNET",
            "geo_country": "UNKNOWN",
        }
        try:
            ip_obj = ipaddress.ip_address(ip_str.strip())
            enrichment["is_private"] = ip_obj.is_private
            enrichment["is_loopback"] = ip_obj.is_loopback

            if ip_obj.is_private:
                enrichment["network_class"] = "INTERNAL_DEFENSE_SUBNET"
                enrichment["geo_country"] = "LOCAL"
            elif ip_obj.is_loopback:
                enrichment["network_class"] = "HOST_LOOPBACK"
                enrichment["geo_country"] = "LOCAL"
            else:
                enrichment["network_class"] = "EXTERNAL_WAN"
                # Deterministic heuristic for Shield Technology regional probes
                s = str(ip_obj)
                if s.startswith("197.14.") or s.startswith("196.203.") or s.startswith("197.3."):
                    enrichment["geo_country"] = "TN"  # Tunisia
                elif s.startswith("45.") or s.startswith("185."):
                    enrichment["geo_country"] = "EU"
                else:
                    enrichment["geo_country"] = "GLOBAL"
        except ValueError:
            enrichment["network_class"] = "INVALID_OR_HOST"

        return enrichment


class EventHasher:
    """Computes deterministic SHA-256 fingerprint for idempotent deduplication."""

    @staticmethod
    def compute_hash(
        agent_id: str,
        timestamp: datetime,
        event_type: str,
        source_ip: str,
        destination_ip: Optional[str],
        payload: Dict[str, Any],
    ) -> Tuple[str, str]:
        iso_ts = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dest = destination_ip or ""
        identity_str = f"{agent_id}|{iso_ts}|{event_type}|{source_ip}|{dest}"
        event_hash = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()

        payload_canonical = json.dumps(payload, sort_keys=True, default=str)
        raw_checksum = hashlib.sha256(payload_canonical.encode("utf-8")).hexdigest()

        return event_hash, raw_checksum
