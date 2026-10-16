"""
Shield Technology - Schema Registry & Message Evolution Engine.
Ensures forward and backward schema compatibility across distributed microservices.
"""

from enum import Enum
import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("shield.schema_registry")


class CompatibilityMode(str, Enum):
    BACKWARD = "BACKWARD"      # New schema can read data written by previous schema
    FORWARD = "FORWARD"        # Previous schema can read data written by new schema
    FULL = "FULL"              # Both backward and forward compatible
    NONE = "NONE"


class SchemaValidationError(Exception):
    pass


class SchemaRegistry:
    """
    Thread-safe Schema Registry governing message evolution and contract enforcement.
    """

    def __init__(self, default_mode: CompatibilityMode = CompatibilityMode.FULL):
        self.default_mode = default_mode
        self._schemas: Dict[str, Dict[str, Dict[str, Any]]] = {}  # topic -> {version: schema_def}
        self._lock = threading.RLock()

        # Seed initial canonical schemas
        self._init_defaults()

    def _init_defaults(self) -> None:
        v1_schema = {
            "version": "v1.0",
            "required_fields": ["event_id", "timestamp_unix_ms", "agent_id", "severity", "event_type", "payload"],
            "field_types": {
                "event_id": "string",
                "timestamp_unix_ms": "int",
                "agent_id": "string",
                "severity": "string",
                "event_type": "string",
                "payload": "object",
            },
            "fingerprint": "a1b2c3d4e5f6",
        }

        v1_1_schema = {
            "version": "v1.1",
            "required_fields": ["event_id", "timestamp_unix_ms", "agent_id", "severity", "event_type", "payload"],
            "optional_fields": ["tenant_id", "source_ip", "destination_ip", "event_hash"],
            "field_types": {
                "event_id": "string",
                "timestamp_unix_ms": "int",
                "agent_id": "string",
                "severity": "string",
                "event_type": "string",
                "payload": "object",
                "tenant_id": "string",
                "source_ip": "string",
                "destination_ip": "string",
                "event_hash": "string",
            },
            "fingerprint": "f6e5d4c3b2a1",
        }

        self.register_schema("telemetry.raw", "v1.0", v1_schema, validate_compat=False)
        self.register_schema("telemetry.raw", "v1.1", v1_1_schema, validate_compat=True)

    @staticmethod
    def compute_fingerprint(schema_def: Dict[str, Any]) -> str:
        serialized = json.dumps(schema_def, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def register_schema(
        self,
        topic: str,
        version: str,
        schema_def: Dict[str, Any],
        validate_compat: bool = True,
    ) -> str:
        """Registers a new schema version under a topic after compatibility check."""
        with self._lock:
            if topic not in self._schemas:
                self._schemas[topic] = {}

            if validate_compat and self._schemas[topic]:
                latest_ver = sorted(self._schemas[topic].keys())[-1]
                prev_schema = self._schemas[topic][latest_ver]
                self._check_compatibility(prev_schema, schema_def, self.default_mode)

            fingerprint = self.compute_fingerprint(schema_def)
            schema_def["fingerprint"] = fingerprint
            schema_def["registered_version"] = version
            self._schemas[topic][version] = schema_def

            logger.info("Registered schema %s:%s (fingerprint: %s)", topic, version, fingerprint)
            return fingerprint

    def _check_compatibility(
        self, prev: Dict[str, Any], next_s: Dict[str, Any], mode: CompatibilityMode
    ) -> None:
        """Enforces schema compatibility rules."""
        prev_req: Set[str] = set(prev.get("required_fields", []))
        next_req: Set[str] = set(next_s.get("required_fields", []))

        prev_types = prev.get("field_types", {})
        next_types = next_s.get("field_types", {})

        # Type mutability check: common fields must retain the same data types
        common_fields = set(prev_types.keys()) & set(next_types.keys())
        for f in common_fields:
            if prev_types[f] != next_types[f]:
                raise SchemaValidationError(
                    f"Type incompatibility on field '{f}': {prev_types[f]} vs {next_types[f]}"
                )

        if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL):
            # In BACKWARD: New schema cannot add new required fields without defaults
            added_required = next_req - prev_req
            if added_required:
                raise SchemaValidationError(
                    f"BACKWARD incompatible: New required fields added {added_required}"
                )

        if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL):
            # In FORWARD: Old required fields cannot be deleted
            removed_required = prev_req - next_req
            if removed_required:
                raise SchemaValidationError(
                    f"FORWARD incompatible: Required fields removed {removed_required}"
                )

    def validate_message(self, topic: str, version: str, message: Dict[str, Any]) -> bool:
        """Validates a payload against a registered schema version."""
        with self._lock:
            if topic not in self._schemas or version not in self._schemas[topic]:
                raise SchemaValidationError(f"Unknown topic or version: {topic}:{version}")

            schema = self._schemas[topic][version]
            for req in schema.get("required_fields", []):
                if req not in message:
                    raise SchemaValidationError(f"Missing required field '{req}' for schema {version}")

            return True

    def get_latest_version(self, topic: str) -> Optional[str]:
        with self._lock:
            if topic not in self._schemas or not self._schemas[topic]:
                return None
            return sorted(self._schemas[topic].keys())[-1]

    def export_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                topic: {
                    ver: {
                        "fingerprint": s["fingerprint"],
                        "required_count": len(s.get("required_fields", [])),
                        "total_fields": len(s.get("field_types", {})),
                    }
                    for ver, s in versions.items()
                }
                for topic, versions in self._schemas.items()
            }


# Singleton instance
schema_registry = SchemaRegistry()
