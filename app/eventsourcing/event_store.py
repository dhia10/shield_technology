"""
Shield Technology - Immutable Event Sourcing & Audit Ledger.
Stores every security state transition as a tamper-evident cryptographically chained event.
Allows deterministic replaying and state reconstruction for forensic investigations.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SourcedEvent:
    event_index: int
    timestamp_iso: str
    aggregate_id: str
    event_type: str
    data: Dict[str, Any]
    prev_hash: str
    current_hash: str = ""

    def compute_hash(self) -> str:
        payload = f"{self.event_index}|{self.timestamp_iso}|{self.aggregate_id}|{self.event_type}|{json.dumps(self.data, sort_keys=True)}|{self.prev_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EventStore:
    """
    Append-only tamper-evident event ledger implementing cryptographic provenance chaining.
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self):
        self._events: List[SourcedEvent] = []
        self._lock = threading.RLock()

    def append(self, aggregate_id: str, event_type: str, data: Dict[str, Any]) -> SourcedEvent:
        """Appends a new immutable event to the chain, linking to the previous hash."""
        with self._lock:
            index = len(self._events)
            prev_hash = self._events[-1].current_hash if self._events else self.GENESIS_HASH
            now_iso = datetime.now(timezone.utc).isoformat()

            ev = SourcedEvent(
                event_index=index,
                timestamp_iso=now_iso,
                aggregate_id=aggregate_id,
                event_type=event_type,
                data=data,
                prev_hash=prev_hash,
            )
            ev.current_hash = ev.compute_hash()
            self._events.append(ev)
            return ev

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verifies the complete cryptographic chain from genesis to head."""
        with self._lock:
            for i, ev in enumerate(self._events):
                expected_prev = self._events[i - 1].current_hash if i > 0 else self.GENESIS_HASH
                if ev.prev_hash != expected_prev:
                    return False, f"Broken chain link at index {i}: expected prev {expected_prev}, got {ev.prev_hash}"
                recomputed = ev.compute_hash()
                if ev.current_hash != recomputed:
                    return False, f"Corrupted event at index {i}: recomputed {recomputed} != {ev.current_hash}"
            return True, None

    def get_aggregate_history(self, aggregate_id: str) -> List[Dict[str, Any]]:
        """Reconstructs the full historical lifecycle of an incident or entity."""
        with self._lock:
            return [asdict(ev) for ev in self._events if ev.aggregate_id == aggregate_id]

    def replay_aggregate_state(self, aggregate_id: str) -> Dict[str, Any]:
        """Replays all events for an aggregate to restore current projection."""
        history = self.get_aggregate_history(aggregate_id)
        state: Dict[str, Any] = {"aggregate_id": aggregate_id, "status": "CREATED", "version": 0}
        for ev in history:
            state["version"] += 1
            ev_type = ev["event_type"]
            data = ev["data"]
            if ev_type == "INCIDENT_DETECTED":
                state["severity"] = data.get("severity")
                state["initial_attack"] = data.get("attack_type")
                state["status"] = "INVESTIGATING"
            elif ev_type == "SEVERITY_ESCALATED":
                state["severity"] = data.get("new_severity")
                state["escalation_reason"] = data.get("reason")
            elif ev_type == "IP_QUARANTINED":
                state["quarantined_ip"] = data.get("ip")
                state["status"] = "CONTAINED"
            elif ev_type == "INCIDENT_RESOLVED":
                state["status"] = "RESOLVED"
                state["resolution"] = data.get("resolution")

        return state

    def count(self) -> int:
        with self._lock:
            return len(self._events)


# Singleton instance
event_store = EventStore()
