"""
Shield Technology - MQTT Network Adapter for Edge & IoT Telemetry.
Ingests sensor metrics and hardware firewall logs from distributed industrial agents.
Translates heterogeneous MQTT topics and compact payloads into canonical internal events.
"""

from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from app.protocols.binary_serializer import BinarySerializer, WireTelemetryEvent
from app.schemas import EventTypeEnum, RawTelemetryEvent, SeverityEnum

logger = logging.getLogger("shield.mqtt")


class MQTTTopicParser:
    """Parses Shield Technology hierarchical MQTT topic patterns:
    Format: shield/telemetry/{tenant_id}/{agent_id}/{event_category}
    Example: shield/telemetry/tenant-alpha/probe-sousse-iot-01/network
    """

    TOPIC_REGEX = re.compile(r"^shield/telemetry/(?P<tenant>[a-zA-Z0-9_\-]+)/(?P<agent>[a-zA-Z0-9_\-]+)/(?P<category>[a-zA-Z0-9_\-]+)$")

    @classmethod
    def parse(cls, topic: str) -> Optional[Dict[str, str]]:
        match = cls.TOPIC_REGEX.match(topic)
        if match:
            return match.groupdict()
        return None


class MQTTTelemetryAdapter:
    """
    Protocol adapter translating incoming MQTT messages (QoS 0/1/2)
    into validated RawTelemetryEvent objects.
    """

    def __init__(self):
        self.total_messages_received = 0
        self.total_bytes_processed = 0
        self.translation_errors = 0

    def process_message(
        self, topic: str, payload_bytes: bytes, qos: int = 1
    ) -> Tuple[bool, Optional[RawTelemetryEvent], Optional[str]]:
        """
        Translates raw MQTT packet into normalized internal event.
        Supports both compact binary wire frames and JSON payload encodings.
        """
        self.total_messages_received += 1
        self.total_bytes_processed += len(payload_bytes)

        # 1. Parse Topic
        meta = MQTTTopicParser.parse(topic)
        if not meta:
            self.translation_errors += 1
            return False, None, f"Invalid topic structure: {topic}"

        tenant_id = meta["tenant"]
        agent_id = meta["agent"]
        category = meta["category"].upper()

        # 2. Decode Payload (Binary or JSON)
        try:
            if payload_bytes.startswith(BinarySerializer.MAGIC_HEADER):
                # Binary serialized frame
                wire_ev = BinarySerializer.deserialize_event(payload_bytes)
                event = RawTelemetryEvent(
                    timestamp=datetime.fromtimestamp(wire_ev.timestamp_unix_ms / 1000.0, tz=timezone.utc),
                    agent_id=wire_ev.agent_id,
                    tenant_id=wire_ev.tenant_id or tenant_id,
                    severity=SeverityEnum.CRITICAL if wire_ev.severity_code >= 4 else SeverityEnum.HIGH if wire_ev.severity_code == 3 else SeverityEnum.MEDIUM if wire_ev.severity_code == 2 else SeverityEnum.LOW,
                    event_type=EventTypeEnum.DDOS_FLOOD if wire_ev.event_type_code == 4 else EventTypeEnum.SQL_INJECTION_ATTEMPT if wire_ev.event_type_code == 3 else EventTypeEnum.SSH_BRUTE_FORCE if wire_ev.event_type_code == 2 else EventTypeEnum.PORT_SCAN,
                    source_ip=".".join(str(b) for b in wire_ev.source_ip_packed),
                    destination_ip=".".join(str(b) for b in wire_ev.destination_ip_packed),
                    payload=json.loads(wire_ev.payload_bytes.decode("utf-8")),
                )
                return True, event, None

            # JSON text payload
            payload_data = json.loads(payload_bytes.decode("utf-8"))
            severity = SeverityEnum(payload_data.get("severity", "MEDIUM"))
            event_type = EventTypeEnum(payload_data.get("event_type", "PORT_SCAN"))

            event = RawTelemetryEvent(
                timestamp=datetime.now(timezone.utc),
                agent_id=agent_id,
                tenant_id=tenant_id,
                severity=severity,
                event_type=event_type,
                source_ip=payload_data.get("source_ip", "127.0.0.1"),
                destination_ip=payload_data.get("destination_ip", "10.0.0.1"),
                payload=payload_data.get("payload", {}),
            )
            return True, event, None

        except Exception as exc:
            self.translation_errors += 1
            logger.error("Failed to translate MQTT message: %s", exc)
            return False, None, str(exc)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_messages_received": self.total_messages_received,
            "total_bytes_processed": self.total_bytes_processed,
            "translation_errors": self.translation_errors,
            "error_rate_percent": round(
                (self.translation_errors / max(1, self.total_messages_received)) * 100.0, 3
            ),
        }


# Singleton adapter instance
mqtt_adapter = MQTTTelemetryAdapter()
